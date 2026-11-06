"""Skill de conversación (fase 5): todo lo que no es una skill concreta.

No tiene patrones: el router por regex nunca la elige. Solo la elige el LLM
(ver asistente/cerebro.py), y ella le pide al LLM que redacte la respuesta.
Solo existe si hay LLM: sin él, esas frases reciben "todavía no sé hacer eso".

Fase 6 (latencia): la respuesta sale por trozos (Respuesta.frases). Piper
empieza con la primera frase mientras el LLM escribe el resto (ADR 0008).
"""
from __future__ import annotations

import logging
from typing import Callable, Iterator

from asistente.skills.base import Peticion, Respuesta, Skill
from asistente.trocear import trocear

log = logging.getLogger(__name__)

# Un modelo de 3B sabe poco y se inventa cosas con mucha seguridad ("una
# araña tiene seis patas"). Estas instrucciones reducen el riesgo, no lo eliminan.
INSTRUCCIONES = (
    "Eres Numa, un asistente de voz en español. Responde en una o dos frases "
    "cortas, sin emojis ni listas: lo que digas se leerá en voz alta. "
    "Si no estás seguro de un dato, dilo con sencillez en vez de inventarlo. "
    "No digas la hora ni el tiempo meteorológico: no los conoces. "
    # Con memoria, el modelo imitaba respuestas anteriores ("Otro temporizador
    # de 5 minutos en marcha") SIN crear nada: mentir sobre una acción es lo
    # peor que puede hacer un asistente. Medido: 2/3 mentiras → 0/3.
    "Tú no puedes hacer acciones: nunca digas que has puesto un temporizador, "
    "una alarma o cualquier otra cosa; si te piden una acción, di que no la "
    "has entendido y que lo repitan."
)


class ConversarSkill(Skill):
    nombre = "conversar"
    descripcion = ("Cualquier otra cosa: saludos, agradecimientos, charla o preguntas "
                   "de cultura general que no sean de las otras intenciones.")

    def __init__(self, charlar_en_flujo: Callable[[str, str, list[dict]], Iterator[str]]) -> None:
        # Recibe la función, no el cliente: así se testea con un LLM falso.
        self._charlar_en_flujo = charlar_en_flujo

    def ejecutar(self, peticion: Peticion) -> Respuesta:
        # Nada se pide al LLM todavía: el flujo es perezoso y arranca cuando
        # la voz pide la primera frase.
        tokens = self._charlar_en_flujo(INSTRUCCIONES, peticion.texto, peticion.historial)
        return Respuesta(texto="", frases=trocear(_a_prueba_de_fallos(tokens)))


def _a_prueba_de_fallos(tokens: Iterator[str]) -> Iterator[str]:
    """Si el LLM falla a mitad, no revienta el bucle principal.

    Las excepciones de un generador salen donde se CONSUME (aquí, dentro de
    voz.decir_frases(), en pleno HABLANDO), no donde se creó: por eso el
    try/except de pensar() ya no las ve y hay que capturarlas aquí.
    """
    dicho = False
    try:
        for token in tokens:
            dicho = dicho or bool(token.strip())
            yield token
    except Exception as e:
        log.warning("El LLM ha fallado a mitad de respuesta: %r", e)
        yield (" Perdona, me he perdido." if dicho
               else " Ahora mismo no puedo pensar en eso, perdona.")
        return
    finally:
        cerrar = getattr(tokens, "close", None)
        if cerrar is not None:
            cerrar()  # cerrar en cadena: si nos interrumpen, que Ollama pare
    if not dicho:
        yield "No sé qué decirte a eso."
