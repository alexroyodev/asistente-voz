"""Bucle principal: entrada por teclado, salida por voz (fase 2).

Ejecuta con:  python -m asistente           (habla con Piper)
              python -m asistente --texto   (solo imprime)
Con -v verás los cambios de estado y cuánto tarda cada respuesta.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from asistente.estado import Estado, MaquinaEstados
from asistente.router import Router
from asistente.skills import cargar_skills
from asistente.voz import Voz, VozPiper, VozTexto

SALIR = {"salir", "adios", "hasta luego"}
MODELO_VOZ = Path("modelos/es_ES-davefx-medium.onnx")


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
    logging.getLogger("piper").setLevel(logging.WARNING)  # con -v vuelca fonemas
    log = logging.getLogger("asistente")

    maquina = MaquinaEstados()
    voz = crear_voz(log)
    router = Router(cargar_skills(voz))
    print("Asistente listo. Escribe 'salir' para terminar.")

    while True:
        try:
            texto = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not texto:
            continue
        if texto.lower() in SALIR:
            print("¡Hasta luego!")
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
