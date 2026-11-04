"""Registro de skills. Para añadir una nueva: créala y añádela aquí."""
from __future__ import annotations

from typing import Callable

from asistente.skills.chiste import ChisteSkill
from asistente.skills.conversar import ConversarSkill
from asistente.skills.hora import HoraSkill
from asistente.skills.temporizador import TemporizadorSkill
from asistente.skills.tiempo import TiempoSkill


def cargar_skills(avisar: Callable[[str], None] = print,
                  charlar: Callable[[str, str], str] | None = None):
    # Las skills que quieren decir algo por su cuenta (fuera del turno de
    # respuesta) reciben `avisar`. En el asistente, avisar publica un
    # evento Aviso en la cola: la skill NO habla, pide que se hable (ADR 0004).
    # Sin nada (p. ej. en los tests), se imprime.
    skills = [
        HoraSkill(),
        TemporizadorSkill(avisar=avisar),
        TiempoSkill(),
        ChisteSkill(),
    ]
    # `conversar` solo existe si hay LLM que redacte (ADR 0006).
    if charlar is not None:
        skills.append(ConversarSkill(charlar))
    return skills
