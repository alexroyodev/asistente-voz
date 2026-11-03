"""Skill de chistes. Reto extra de la fase 1. Te toca a ti 🙂

Objetivo: "cuéntame un chiste" -> responde con un chiste de la lista, sin
repetir el mismo dos veces seguidas.
"""
from __future__ import annotations

import random

from asistente.skills.base import Peticion, Respuesta, Skill

# Cortos y fáciles de decir en voz alta: en la fase 2 los leerá Piper.
CHISTES = (
    "¿Qué le dice una iguana a su hermana gemela? Iguanita.",
    "¿Por qué el libro de matemáticas está triste? Porque tiene muchos problemas.",
    "¿Cómo se despiden los químicos? Ácido un placer.",
    "¿Qué hace una abeja en el gimnasio? Zum-ba.",
    "¿Cuál es el café más peligroso del mundo? El ex-preso.",
    "¿Qué le dice un techo a otro? Techo de menos.",
)


class ChisteSkill(Skill):
    nombre = "chiste"
    descripcion = "Cuenta un chiste corto."
    patrones = (r"\bchistes?\b", r"\bhazme reir\b")

    def __init__(self, chistes=CHISTES, aleatorio: random.Random | None = None) -> None:
        # Inyectamos la lista y el generador aleatorio para poder testear
        # con una semilla fija (resultados reproducibles).
        self._chistes = chistes
        self._aleatorio = aleatorio or random.Random()
        self._ultimo: str | None = None

    def ejecutar(self, peticion: Peticion) -> Respuesta:
        # Para tu diario: ¿por qué guardar estado en la skill funciona hoy,
        # pero sería un problema si dos usuarios hablaran con el mismo
        # asistente (fase 7, varios satélites)?
        # Candidatos = todos menos el último; si no queda ninguno (un solo
        # chiste, o todos iguales), se permite repetir.
        candidatos = [c for c in self._chistes if c != self._ultimo] or self._chistes
        chiste = self._aleatorio.choice(candidatos)
        self._ultimo = chiste
        return Respuesta(chiste)
