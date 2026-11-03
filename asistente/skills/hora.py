"""Skill de la hora. Dice la hora como lo haría una persona, no un reloj
digital: "Son las 6 menos 12", no "Son las 17:48".

Los números van en cifras: Piper ya los lee bien ("6" -> "seis").
"""
from __future__ import annotations

from datetime import datetime

from asistente.skills.base import Peticion, Respuesta, Skill


def decir_hora(hora: int, minuto: int) -> str:
    """Convierte hora (0-23) y minuto (0-59) en una frase hablada.

    Ejemplos (los tests de tests/test_basicos.py tienen la lista completa):
        9:00  -> "Son las 9 en punto."
        9:15  -> "Son las 9 y cuarto."
        17:48 -> "Son las 6 menos 12."
        12:45 -> "Es la 1 menos cuarto."
    """
    # Para tu diario: ¿qué pasa a las 23:50? ¿Y a las 12:50?
    hora_12 = hora % 12
    if hora_12 == 0:
        hora_12 = 12

    # 1. Las partes: de qué hora hablamos y qué va detrás.
    if minuto <= 30:
        hora_final = hora_12
        resto = {0: "en punto", 15: "y cuarto", 30: "y media"}.get(minuto, f"y {minuto}")
    else:
        hora_final = (hora_12 % 12) + 1  # 12 -> 1, nunca 13
        resto = "menos cuarto" if minuto == 45 else f"menos {60 - minuto}"

    # 2. El artículo, decidido una sola vez. 3. Se monta la frase.
    articulo = "Es la" if hora_final == 1 else "Son las"
    return f"{articulo} {hora_final} {resto}."


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
        return Respuesta(decir_hora(t.hour, t.minute))
