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
        9:00  -> "Son las 9 en punto de la mañana."
        17:48 -> "Son las 6 menos 12 de la tarde."
        12:45 -> "Es la 1 menos cuarto de la tarde."
        12:00 -> "Son las 12 del mediodía."

    Franjas (decididas el 2026-11-03), según la hora QUE SE DICE en 24 h:
        1-5 madrugada · 6-12 mañana · 13-20 tarde · 21-0 noche
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

    # 2. La franja, según la hora QUE SE DICE en 24 h. Se calcula desde
    #    hora/minuto originales: hora_final (12 h) ya no distingue 6 de 18.
    hora_dicha = hora if minuto <= 30 else (hora + 1) % 24
    if 1 <= hora_dicha <= 5:
        franja = "de la madrugada"
    elif 6 <= hora_dicha <= 12:
        franja = "de la mañana"
    elif 13 <= hora_dicha <= 20:
        franja = "de la tarde"
    else:  # 21-23 y 0: la única franja que cruza la medianoche
        franja = "de la noche"

    # 3. Lo que va detrás de la hora. Los especiales SUSTITUYEN a
    #    "en punto" + franja; no se añaden.
    if minuto == 0 and hora_dicha == 12:
        complemento = "del mediodía"
    elif minuto == 0 and hora_dicha == 0:
        complemento = "de la noche"
    else:
        complemento = f"{resto} {franja}"

    # 4. El artículo, decidido una sola vez. 5. Se monta la frase.
    articulo = "Es la" if hora_final == 1 else "Son las"
    return f"{articulo} {hora_final} {complemento}."


class HoraSkill(Skill):
    nombre = "hora"
    descripcion = "Decir la hora actual, o responder algo que dependa de ella (¿llego tarde?)."
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
