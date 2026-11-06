"""Partir un texto que llega por trozos (tokens del LLM) en frases para Piper.

Piper entona cada frase completa, así que no se le pueden pasar tokens
sueltos; pero esperar al texto entero es justo lo que queremos evitar
(fase 6, latencia: ver ADR 0008). Se corta:

  1. en fin de frase (. ! ? …) seguido de espacio, si el trozo tiene al
     menos MINIMO caracteres ("Sí." no se manda solo: se junta con lo
     siguiente, y "a.C., con" no se parte porque tras el punto va una coma);
  2. si no hay fin de frase y el trozo ya pasa de LARGO caracteres, en la
     última coma (o ; :) seguida de espacio: una frase de 220 caracteres
     empezaría a sonar tarde.

Limitación: "en el 753 a.C. según" sí se parte tras "a.C." (abreviatura
seguida de espacio). Una pausa rara, no un error.
"""
from __future__ import annotations

import re
from typing import Iterable, Iterator

MINIMO = 12
LARGO = 80
_FIN_DE_FRASE = re.compile(r"[.!?…]+(?=\s)")
_PAUSA = re.compile(r"[,;:](?=\s)")


def buscar_corte(texto: str, minimo: int = MINIMO, largo: int = LARGO) -> int | None:
    """Posición donde cortar `texto`, o None si aún no hay un trozo listo."""
    for m in _FIN_DE_FRASE.finditer(texto):
        if m.end() >= minimo:
            return m.end()
    if len(texto) >= largo:
        pausas = [m.end() for m in _PAUSA.finditer(texto) if m.end() >= minimo]
        if pausas:
            return pausas[-1]
    return None


def trocear(trozos: Iterable[str], minimo: int = MINIMO, largo: int = LARGO) -> Iterator[str]:
    """Tokens → frases, en cuanto cada una está lista. Lo que sobre, al final."""
    pendiente = ""
    for trozo in trozos:
        pendiente += trozo
        while (corte := buscar_corte(pendiente, minimo, largo)) is not None:
            frase, pendiente = pendiente[:corte].strip(), pendiente[corte:]
            if frase:
                yield frase
    if pendiente.strip():
        yield pendiente.strip()
