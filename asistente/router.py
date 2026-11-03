"""Router de intenciones: decide qué skill atiende cada frase.

Fase 1: reglas con expresiones regulares (rápido, predecible, sin GPU).
Fase 5: si ninguna regla encaja, se pasará la frase a un LLM. Las reglas
se quedan como "vía rápida" para comandos simples.
"""
from __future__ import annotations

import re
import unicodedata

from asistente.skills.base import Peticion, Skill


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni signos, espacios simples.

    "¿Qué HORA es?" -> "que hora es". Así los patrones son más sencillos y
    funcionan igual con lo que transcriba Whisper más adelante.
    """
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^\w\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


class Router:
    def __init__(self, skills: list[Skill]) -> None:
        self._reglas: list[tuple[re.Pattern[str], Skill]] = [
            (re.compile(p), skill) for skill in skills for p in skill.patrones
        ]

    def resolver(self, texto: str) -> tuple[Skill, Peticion] | None:
        """Devuelve la primera skill cuyo patrón encaje, o None."""
        normal = normalizar(texto)
        for patron, skill in self._reglas:
            m = patron.search(normal)
            if m:
                entidades = {k: v for k, v in m.groupdict().items() if v is not None}
                return skill, Peticion(texto=normal, entidades=entidades)
        return None
