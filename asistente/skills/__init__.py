"""Registro de skills. Para añadir una nueva: créala y añádela aquí."""
from __future__ import annotations

from asistente.skills.chiste import ChisteSkill
from asistente.skills.hora import HoraSkill
from asistente.skills.temporizador import TemporizadorSkill
from asistente.skills.tiempo import TiempoSkill
from asistente.voz import Voz, VozTexto


def cargar_skills(voz: Voz | None = None):
    # Las skills que hablan por su cuenta (fuera del turno de respuesta)
    # reciben la voz aquí. Sin voz (p. ej. en los tests), se imprime.
    voz = voz or VozTexto()
    return [
        HoraSkill(),
        TemporizadorSkill(avisar=voz.decir),
        TiempoSkill(),
        ChisteSkill(),
    ]
