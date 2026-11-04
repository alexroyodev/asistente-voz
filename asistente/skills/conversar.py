"""Skill de conversación (fase 5): todo lo que no es una skill concreta.

No tiene patrones: el router por regex nunca la elige. Solo la elige el LLM
(ver asistente/cerebro.py), y ella le pide al LLM que redacte la respuesta.
Solo existe si hay LLM: sin él, esas frases reciben "todavía no sé hacer eso".
"""
from __future__ import annotations

from typing import Callable

from asistente.skills.base import Peticion, Respuesta, Skill

# Un modelo de 3B sabe poco y se inventa cosas con mucha seguridad ("una
# araña tiene seis patas"). Estas instrucciones reducen el riesgo, no lo eliminan.
INSTRUCCIONES = (
    "Eres Numa, un asistente de voz en español. Responde en una o dos frases "
    "cortas, sin emojis ni listas: lo que digas se leerá en voz alta. "
    "Si no estás seguro de un dato, dilo con sencillez en vez de inventarlo. "
    "No digas la hora ni el tiempo meteorológico: no los conoces."
)


class ConversarSkill(Skill):
    nombre = "conversar"
    descripcion = ("Cualquier otra cosa: saludos, agradecimientos, charla o preguntas "
                   "de cultura general que no sean de las otras intenciones.")

    def __init__(self, charlar: Callable[[str, str], str]) -> None:
        # Recibe la función, no el cliente: así se testea con un LLM falso.
        self._charlar = charlar

    def ejecutar(self, peticion: Peticion) -> Respuesta:
        try:
            texto = self._charlar(INSTRUCCIONES, peticion.texto)
        except Exception:
            return Respuesta("Ahora mismo no puedo pensar en eso, perdona.")
        return Respuesta(texto or "No sé qué decirte a eso.")
