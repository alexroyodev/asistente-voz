"""Bucle principal: entrada por micrófono o teclado, salida por voz o pantalla.

Ejecuta con:  python -m asistente                    (micrófono + Piper)
              python -m asistente --teclado          (escribes en vez de hablar)
              python -m asistente --texto            (imprime en vez de hablar)
              python -m asistente --whisper small    (otro modelo de Whisper)
Con -v verás los cambios de estado y cuánto tarda cada paso.

Arquitectura (ver ADR 0004): productor-consumidor.
  - Productores (otros hilos) solo publican eventos en la cola.
  - Este hilo es el ÚNICO consumidor: el único que habla, escucha, imprime
    el prompt y cambia de estado. Por eso no puede haber eco.
"""
from __future__ import annotations

import logging
import queue
import sys
import time
from pathlib import Path

from asistente.entrada import iniciar_entrada
from asistente.estado import Estado, MaquinaEstados
from asistente.eventos import Activar, Aviso, Evento, Frase, Salir
from asistente.oido import Oido, OidoWhisper
from asistente.router import Router, normalizar
from asistente.skills import cargar_skills
from asistente.voz import Voz, VozPiper, VozTexto

SALIR = {"salir", "adios", "hasta luego"}
MODELO_VOZ = Path("modelos/es_ES-davefx-medium.onnx")
WHISPER_POR_DEFECTO = "turbo"  # "small" ahorra ~550 MiB de VRAM (ver ADR 0003)


def opcion(nombre: str, defecto: str) -> str:
    """Valor tras `nombre` en la línea de órdenes (--whisper small)."""
    if nombre in sys.argv:
        i = sys.argv.index(nombre)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return defecto


def crear_oido(log: logging.Logger) -> Oido | None:
    if "--teclado" in sys.argv:
        return None  # el texto llega ya hecho en eventos Frase
    modelo = opcion("--whisper", WHISPER_POR_DEFECTO)
    inicio = time.perf_counter()
    oido = OidoWhisper(modelo)
    log.debug("Whisper %s cargado en %.0f ms", modelo, (time.perf_counter() - inicio) * 1000)
    return oido


def crear_voz(log: logging.Logger) -> Voz:
    if "--texto" in sys.argv:
        return VozTexto()
    if not MODELO_VOZ.exists():
        sys.exit(
            f"No encuentro la voz en {MODELO_VOZ}. Descárgala con:\n"
            "  python -m piper.download_voices es_ES-davefx-medium --data-dir modelos\n"
            "o arranca sin voz con --texto."
        )
    inicio = time.perf_counter()
    voz = VozPiper(MODELO_VOZ)
    log.debug("Voz cargada en %.0f ms", (time.perf_counter() - inicio) * 1000)
    return voz


def esperar_evento(cola: queue.Queue[Evento]) -> Evento:
    """Como cola.get(), pero dejando pasar Ctrl+C.

    En Windows, un get() sin timeout bloquea en un lock que la señal de
    Ctrl+C no despierta. Con timeout, cada 0,2 s Python recupera el control
    y puede lanzar KeyboardInterrupt.
    """
    while True:
        try:
            return cola.get(timeout=0.2)
        except queue.Empty:
            continue


def pensar(router: Router, texto: str, log: logging.Logger) -> str:
    """Router + skill: de una frase a la respuesta. Nunca lanza."""
    resultado = router.resolver(texto)
    if resultado is None:
        return "Lo siento, todavía no sé hacer eso."
    skill, peticion = resultado
    try:
        return skill.ejecutar(peticion).texto
    except Exception:
        log.exception("Fallo en la skill %s", skill.nombre)
        return "Uy, algo ha fallado al hacer eso."


def main() -> None:
    nivel = logging.DEBUG if "-v" in sys.argv else logging.WARNING
    logging.basicConfig(level=nivel, format="%(levelname)s %(name)s: %(message)s")
    # Con -v solo queremos NUESTRO log; estas librerías vuelcan sus detalles.
    for ruidosa in ("piper", "faster_whisper", "httpx", "httpx2", "httpcore",
                    "httpcore2", "huggingface_hub", "urllib3"):
        logging.getLogger(ruidosa).setLevel(logging.WARNING)
    log = logging.getLogger("asistente")

    maquina = MaquinaEstados()
    voz = crear_voz(log)
    oido = crear_oido(log)
    cola: queue.Queue[Evento] = queue.Queue()
    # Productor: el temporizador (en su hilo) solo publica; hablará este hilo.
    router = Router(cargar_skills(avisar=lambda texto: cola.put(Aviso(texto))))
    iniciar_entrada(cola, con_texto=oido is None)
    prompt = "> " if oido is None else "[Enter para hablar] "

    def responder(texto: str) -> bool:
        """PENSANDO → HABLANDO → REPOSO. Devuelve False si hay que salir."""
        # normalizar: Whisper devuelve "¡Adiós!" o "Salir." con signos y tildes.
        if normalizar(texto) in SALIR:
            voz.decir("¡Hasta luego!")
            return False
        inicio = time.perf_counter()
        maquina.transicionar(Estado.PENSANDO)
        respuesta = pensar(router, texto, log)
        # decir() bloquea: medir al final incluiría la duración del audio.
        log.debug("Pensado en %.0f ms", (time.perf_counter() - inicio) * 1000)
        maquina.transicionar(Estado.HABLANDO)
        voz.decir(respuesta)
        maquina.transicionar(Estado.REPOSO)
        return True

    print("Asistente listo. Di o escribe 'salir' para terminar (o Ctrl+C).")
    seguir = True
    while seguir:
        # Solo se imprime el prompt cuando de verdad estamos listos (REPOSO).
        print(prompt, end="", flush=True)
        try:
            evento = esperar_evento(cola)
            log.debug("Evento: %r", evento)
            match evento:
                case Frase(texto=texto):           # ⑦ teclado: REPOSO → PENSANDO
                    seguir = responder(texto)
                case Activar():                    # ① micrófono
                    maquina.transicionar(Estado.ESCUCHANDO)
                    texto = oido.escuchar()
                    if texto is None:              # ② no se entendió nada
                        maquina.transicionar(Estado.REPOSO)
                    else:                          # ③ ESCUCHANDO → PENSANDO
                        seguir = responder(texto)
                case Aviso(texto=texto):           # ⑥ aviso proactivo
                    print()  # el prompt ya estaba impreso: el aviso, en su línea
                    maquina.transicionar(Estado.HABLANDO)
                    voz.decir(texto)
                    maquina.transicionar(Estado.REPOSO)
                case Salir():
                    seguir = False
        except KeyboardInterrupt:
            seguir = False
    print()


if __name__ == "__main__":
    main()
