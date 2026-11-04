"""Skill de temporizador. Te toca a ti 🙂

Objetivo: "pon un temporizador de 5 minutos" -> responde enseguida
("Temporizador de 5 minutos en marcha.") y, cuando pase el tiempo, avisa
por pantalla sin bloquear al asistente mientras tanto.
"""
from __future__ import annotations

import threading

from asistente.skills.base import Peticion, Respuesta, Skill

SEGUNDOS_POR_UNIDAD = {"segundo": 1, "minuto": 60, "hora": 3600}


class TemporizadorSkill(Skill):
    nombre = "temporizador"
    descripcion = ("Avisar cuando pase un tiempo: temporizador, alarma, "
                   "'avísame dentro de…'. Rellena cantidad y unidad.")
    # La regex extrae "cantidad" y "unidad"; `parametros` le dice al LLM que
    # extraiga las mismas, con los mismos nombres.
    patrones = (
        r"temporizador de (?P<cantidad>\d+) (?P<unidad>segundo|minuto|hora)s?",
    )
    parametros = {
        "cantidad": {"type": "integer", "minimum": 1},
        "unidad": {"type": "string", "enum": list(SEGUNDOS_POR_UNIDAD)},
    }

    def __init__(self, avisar=print) -> None:
        # `avisar` es la función que se llama al terminar. Hoy es print;
        # en la fase 2 será "decirlo en voz alta".
        self._avisar = avisar

    def ejecutar(self, peticion: Peticion) -> Respuesta:
        # Para tu diario: ¿qué pasa con los temporizadores pendientes si
        # cierras el programa? ¿Y si pides dos a la vez?
        cantidad = int(peticion.entidades["cantidad"])
        unidad = peticion.entidades["unidad"]
        duracion = f"{cantidad} {unidad}" if cantidad == 1 else f"{cantidad} {unidad}s"

        timer = threading.Timer(
            cantidad * SEGUNDOS_POR_UNIDAD[unidad],
            self._avisar,
            args=[f"¡Tiempo! Han pasado {duracion}."],
        )
        timer.daemon = True  # no impide cerrar el programa
        timer.start()
        return Respuesta(f"Temporizador de {duracion} en marcha.")
