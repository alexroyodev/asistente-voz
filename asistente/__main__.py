"""Bucle principal: entrada por micrófono o teclado, salida por voz o pantalla.

Ejecuta con:  python -m asistente                    (micrófono + Piper)
              python -m asistente --teclado          (escribes en vez de hablar)
              python -m asistente --texto            (imprime en vez de hablar)
              python -m asistente --whisper small    (otro modelo de Whisper)
              python -m asistente --sin-numa         (solo Enter, sin "Oye Numa")
              python -m asistente --sin-llm          (solo reglas, sin Ollama)
              python -m asistente --llm qwen3:4b     (otro modelo de Ollama)
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
import threading
import time
from pathlib import Path

from asistente.activacion import iniciar_activacion
from asistente.cerebro import MODELO_POR_DEFECTO, Cerebro, ClienteLLM
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


def crear_llm(log: logging.Logger) -> ClienteLLM | None:
    """El LLM es opcional: si Ollama no está, el asistente sigue sin él (ADR 0006)."""
    if "--sin-llm" in sys.argv:
        return None
    modelo = opcion("--llm", MODELO_POR_DEFECTO)
    inicio = time.perf_counter()
    try:
        llm = ClienteLLM(modelo)
        llm.precargar()  # ~6 s ahora, en vez de en la primera pregunta
    except Exception as e:
        print(f"Aviso: sigo sin LLM ({modelo}): {e}\n"
              "  ¿Está Ollama en marcha? ¿Hiciste `ollama pull " + modelo + "`?")
        return None
    log.debug("LLM %s cargado en %.0f ms", modelo, (time.perf_counter() - inicio) * 1000)
    return llm


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


def pensar(router: Router, cerebro: Cerebro | None, texto: str,
           log: logging.Logger) -> str:
    """Regex primero (0 ms, nunca falla); si no encaja, el LLM. Nunca lanza."""
    resultado = router.resolver(texto)
    if resultado is None and cerebro is not None:
        inicio = time.perf_counter()
        resultado = cerebro.resolver(texto)
        log.debug("El LLM ha elegido %s en %.0f ms",
                  resultado[0].nombre if resultado else None,
                  (time.perf_counter() - inicio) * 1000)
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
    llm = crear_llm(log)
    skills = cargar_skills(avisar=lambda texto: cola.put(Aviso(texto)),
                           charlar=llm.charlar if llm else None)
    router = Router(skills)
    cerebro = Cerebro(llm, skills) if llm else None
    iniciar_entrada(cola, con_texto=oido is None)

    # El detector de "Oye Numa" solo escucha cuando este hilo le da paso
    # (en REPOSO): nunca se activa con la voz de Piper ni con tu orden.
    escuchando_numa = threading.Event()
    con_numa = oido is not None and "--sin-numa" not in sys.argv
    if con_numa:
        iniciar_activacion(cola, oido.transcribir, escuchando_numa)  # mismo Whisper
    if oido is None:
        prompt = "> "
    elif con_numa:
        prompt = "[Di «Oye Numa» o pulsa Enter] "
    else:
        prompt = "[Enter para hablar] "

    def responder(texto: str) -> bool:
        """PENSANDO → HABLANDO → REPOSO. Devuelve False si hay que salir."""
        # normalizar: Whisper devuelve "¡Adiós!" o "Salir." con signos y tildes.
        if normalizar(texto) in SALIR:
            voz.decir("¡Hasta luego!")
            return False
        inicio = time.perf_counter()
        maquina.transicionar(Estado.PENSANDO)
        respuesta = pensar(router, cerebro, texto, log)
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
            escuchando_numa.set()      # REPOSO: el detector puede escuchar
            evento = esperar_evento(cola)
            escuchando_numa.clear()    # atendemos el evento: el detector, en pausa
            log.debug("Evento: %r", evento)
            match evento:
                case Frase(texto=texto):           # ⑦ teclado u "Oye Numa, <orden>"
                    if oido is not None:           # con micro, una Frase viene de la voz
                        print()  # el prompt ya estaba impreso
                        print(f"  🎙  {texto}")
                    seguir = responder(texto)
                case Activar():                    # ① Enter u "Oye Numa" a secas
                    maquina.transicionar(Estado.ESCUCHANDO)
                    voz.pitar()                    # bloquea: el micro no graba el bip
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
    # Lo hace el hilo principal, no un finally de un hilo daemon (que no
    # se ejecutaría al salir: ver "hilos daemon" en el diario).
    if llm is not None:
        llm.descargar()


if __name__ == "__main__":
    main()
