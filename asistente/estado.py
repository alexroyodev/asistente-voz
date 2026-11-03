"""Máquina de estados del asistente.

En la fase 1 (modo texto) solo se usan REPOSO -> PENSANDO -> REPOSO, pero
la definimos completa desde ya: cuando lleguen el audio y la palabra de
activación, este archivo será el corazón del sistema.

    REPOSO ──(wake word)──▶ ESCUCHANDO ──(fin de frase)──▶ PENSANDO
       ▲                                                      │
       └──────────(fin del audio)── HABLANDO ◀──(respuesta)───┘
"""
from __future__ import annotations

import logging
from enum import Enum, auto

log = logging.getLogger(__name__)


class Estado(Enum):
    REPOSO = auto()
    ESCUCHANDO = auto()
    PENSANDO = auto()
    HABLANDO = auto()


# Transiciones permitidas: desde cada estado, a cuáles se puede ir.
TRANSICIONES: dict[Estado, set[Estado]] = {
    Estado.REPOSO: {Estado.ESCUCHANDO, Estado.PENSANDO},  # PENSANDO: atajo del modo texto
    Estado.ESCUCHANDO: {Estado.PENSANDO, Estado.REPOSO},  # REPOSO: no se entendió nada
    Estado.PENSANDO: {Estado.HABLANDO, Estado.REPOSO},
    Estado.HABLANDO: {Estado.REPOSO, Estado.ESCUCHANDO},  # ESCUCHANDO: interrupción (fase 6)
}


class TransicionInvalida(Exception):
    pass


class MaquinaEstados:
    def __init__(self) -> None:
        self.estado = Estado.REPOSO

    def transicionar(self, nuevo: Estado) -> None:
        # Pregunta para tu diario: ¿por qué conviene fallar ruidosamente aquí
        # en vez de ignorar la transición?
        if nuevo not in TRANSICIONES[self.estado]:
            raise TransicionInvalida(f"{self.estado.name} -> {nuevo.name}")
        log.debug("Estado: %s -> %s", self.estado.name, nuevo.name)
        self.estado = nuevo
