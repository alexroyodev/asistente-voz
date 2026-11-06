"""Contrato común para todas las habilidades (skills) del asistente.

Cualquier skill nueva hereda de `Skill`, declara sus patrones e implementa
`ejecutar`. El núcleo nunca necesita saber qué hace cada skill por dentro:
solo le pasa una `Peticion` y recibe una `Respuesta`.

Fase 5: este mismo contrato (nombre + descripción + parámetros) es lo que el
LLM recibe para elegir skill cuando ninguna regex encaja (ver asistente/cerebro.py).
Por eso `descripcion` va dirigida al LLM: di cuándo usar la skill, con ejemplos.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class Peticion:
    """Lo que el usuario ha pedido, ya convertido a texto."""

    texto: str
    # Datos extraídos del texto: por el router (grupos con nombre de la regex)
    # o por el LLM (según `parametros`). Siempre texto, venga de donde venga:
    # {"cantidad": "5", "unidad": "minuto"}.
    entidades: dict[str, str] = field(default_factory=dict)


@dataclass
class Respuesta:
    """Lo que el asistente va a decir.

    Casi todas las skills tienen la respuesta entera al momento: `texto`.
    Las que la generan poco a poco (el LLM) pueden dar `frases`: un iterador
    que entrega cada frase en cuanto está lista, para que Piper empiece a
    hablar antes de que exista la respuesta completa (ADR 0008).
    """

    texto: str
    fin_conversacion: bool = False
    frases: Iterator[str] | None = None


class Skill(ABC):
    nombre: str = "sin_nombre"
    descripcion: str = ""
    # Expresiones regulares que activan la skill. Se comparan contra el texto
    # normalizado (minúsculas, sin tildes). Usa grupos con nombre (?P<x>...)
    # para extraer entidades.
    patrones: tuple[str, ...] = ()
    # Entidades que la skill necesita, en JSON Schema, para que el LLM sepa
    # extraerlas: {"cantidad": {"type": "integer"}, ...}. Todas obligatorias.
    # Deben llamarse igual que los grupos con nombre de `patrones`.
    parametros: dict[str, dict] = {}

    @abstractmethod
    def ejecutar(self, peticion: Peticion) -> Respuesta:
        """Hace el trabajo y devuelve qué responder."""
