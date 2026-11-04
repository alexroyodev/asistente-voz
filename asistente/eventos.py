"""Eventos: los mensajes que los productores meten en la cola del bucle principal.

Regla de oro (ver ADR 0004): los otros hilos NO actúan, solo avisan. El hilo
principal es el único que habla, escucha y cambia de estado.

    Productor               Evento            Qué hace el bucle principal
    ─────────────────────   ───────────────   ────────────────────────────────
    hilo de entrada (Enter) Activar()         ESCUCHANDO: graba con el micro
    hilo de entrada (texto) Frase(texto)      PENSANDO: router + skill
    temporizador            Aviso(texto)      HABLANDO: lo dice
    hilo de entrada (EOF)   Salir()           termina

En la fase 4, la palabra de activación producirá Activar(): el bucle no cambia.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Activar:
    """El usuario quiere hablar (hoy: Enter; fase 4: palabra de activación)."""


@dataclass(frozen=True)
class Frase:
    """Texto ya listo para el router (modo --teclado)."""

    texto: str


@dataclass(frozen=True)
class Aviso:
    """Algo que el asistente debe decir por iniciativa propia."""

    texto: str


@dataclass(frozen=True)
class Salir:
    """Terminar el programa (Ctrl+Z/Ctrl+D en el teclado)."""


Evento = Activar | Frase | Aviso | Salir
