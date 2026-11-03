"""Skill de ejemplo, completa. Úsala como plantilla para las demás."""
from __future__ import annotations

from datetime import datetime

from asistente.skills.base import Peticion, Respuesta, Skill


class HoraSkill(Skill):
    nombre = "hora"
    descripcion = "Dice la hora actual."
    patrones = (
        r"\bque hora es\b",
        r"\bdime la hora\b",
        r"\bhora\b.*\bes\b",
    )

    def __init__(self, ahora=datetime.now) -> None:
        # Inyectamos el reloj para poder testear con una hora fija.
        self._ahora = ahora

    def ejecutar(self, peticion: Peticion) -> Respuesta:
        t = self._ahora()
        if t.hour == 1:
            return Respuesta(f"Es la una y {t.minute:02d}.")
        return Respuesta(f"Son las {t.hour}:{t.minute:02d}.")
