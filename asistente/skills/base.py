"""Contrato común para todas las habilidades (skills) del asistente.

Cualquier skill nueva hereda de `Skill`, declara sus patrones e implementa
`ejecutar`. El núcleo nunca necesita saber qué hace cada skill por dentro:
solo le pasa una `Peticion` y recibe una `Respuesta`.

Pista para la fase 5: este mismo contrato (nombre + descripción + parámetros)
es casi exactamente lo que un LLM necesita para usar tus skills como "tools".
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Peticion:
    """Lo que el usuario ha pedido, ya convertido a texto."""

    texto: str
    # Datos extraídos del texto por el router (grupos con nombre de la regex),
    # por ejemplo {"cantidad": "5", "unidad": "minutos"}.
    entidades: dict[str, str] = field(default_factory=dict)


@dataclass
class Respuesta:
    """Lo que el asistente va a decir (de momento, a imprimir)."""

    texto: str
    fin_conversacion: bool = False


class Skill(ABC):
    nombre: str = "sin_nombre"
    descripcion: str = ""
    # Expresiones regulares que activan la skill. Se comparan contra el texto
    # normalizado (minúsculas, sin tildes). Usa grupos con nombre (?P<x>...)
    # para extraer entidades.
    patrones: tuple[str, ...] = ()

    @abstractmethod
    def ejecutar(self, peticion: Peticion) -> Respuesta:
        """Hace el trabajo y devuelve qué responder."""
