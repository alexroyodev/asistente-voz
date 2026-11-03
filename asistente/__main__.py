"""Bucle principal: entrada por micrófono o teclado, salida por voz o pantalla.

Ejecuta con:  python -m asistente                    (micrófono + Piper)
              python -m asistente --teclado          (escribes en vez de hablar)
              python -m asistente --texto            (imprime en vez de hablar)
              python -m asistente --whisper small    (otro modelo de Whisper)
Con -v verás los cambios de estado y cuánto tarda cada paso.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from asistente.estado import Estado, MaquinaEstados
from asistente.oido import Oido, OidoTeclado, OidoWhisper
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


def crear_oido(log: logging.Logger) -> Oido:
    if "--teclado" in sys.argv:
        return OidoTeclado()
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
    router = Router(cargar_skills(voz))
    print("Asistente listo. Di o escribe 'salir' para terminar (o Ctrl+C).")

    while True:
        maquina.transicionar(Estado.ESCUCHANDO)
        try:
            texto = oido.escuchar()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if texto is None:
            maquina.transicionar(Estado.REPOSO)  # no se entendió nada: ni se responde
            continue
        # normalizar: Whisper devuelve "¡Adiós!" o "Salir." con signos y tildes.
        if normalizar(texto) in SALIR:
            voz.decir("¡Hasta luego!")
            break

        inicio = time.perf_counter()
        maquina.transicionar(Estado.PENSANDO)

        resultado = router.resolver(texto)
        if resultado is None:
            respuesta = "Lo siento, todavía no sé hacer eso."
        else:
            skill, peticion = resultado
            try:
                respuesta = skill.ejecutar(peticion).texto
            except NotImplementedError as e:
                respuesta = f"[pendiente] {e}"
            except Exception:
                log.exception("Fallo en la skill %s", skill.nombre)
                respuesta = "Uy, algo ha fallado al hacer eso."

        # Como decir() bloquea, medir solo al final incluiría la duración del
        # audio. Lo que el usuario percibe es cuánto tarda en EMPEZAR a oírla.
        log.debug("Pensado en %.0f ms", (time.perf_counter() - inicio) * 1000)
        maquina.transicionar(Estado.HABLANDO)
        voz.decir(respuesta)  # bloquea: HABLANDO dura lo que dura el audio
        maquina.transicionar(Estado.REPOSO)
        log.debug("Turno completo en %.0f ms", (time.perf_counter() - inicio) * 1000)


if __name__ == "__main__":
    main()
