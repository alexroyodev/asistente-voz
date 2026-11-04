"""Skill del tiempo con Open-Meteo (gratis, sin clave). Te toca a ti 🙂

Documentación: https://open-meteo.com/en/docs
Ejemplo de URL (Madrid, tiempo actual):
https://api.open-meteo.com/v1/forecast?latitude=40.42&longitude=-3.70&current=temperature_2m,weather_code
"""
from __future__ import annotations

import json
import logging
import urllib.request

from asistente.skills.base import Peticion, Respuesta, Skill

log = logging.getLogger(__name__)

# Ajusta a tu ubicación (o hazlo configurable: buen ejercicio).
LATITUD = 40.42
LONGITUD = -3.70

# Los códigos WMO que devuelve Open-Meteo. Amplía la tabla a tu gusto.
DESCRIPCION_WMO = {
    0: "despejado",
    1: "mayormente despejado",
    2: "parcialmente nublado",
    3: "nublado",
    61: "lluvia débil",
    63: "lluvia",
}


def pedir_json(url: str, timeout: float = 5.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


class TiempoSkill(Skill):
    nombre = "tiempo"
    descripcion = ("El tiempo meteorológico de ahora: temperatura, lluvia, frío, calor, "
                   "si hace falta paraguas o abrigo.")
    patrones = (r"\bque tiempo hace\b", r"\b(va a llover|hace frio|hace calor)\b")

    def __init__(self, obtener=pedir_json) -> None:
        # Inyectamos la función de red para poder testear sin internet.
        self._obtener = obtener

    def ejecutar(self, peticion: Peticion) -> Respuesta:
        # Para tu diario: ¿cuánto tarda la llamada? Mídelo; en un asistente
        # de voz cada segundo de espera se nota muchísimo.
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={LATITUD}&longitude={LONGITUD}"
            "&current=temperature_2m,weather_code"
        )
        try:
            actual = self._obtener(url)["current"]
            temperatura = round(actual["temperature_2m"])
            codigo = actual["weather_code"]
        except (OSError, KeyError, ValueError, TypeError) as e:
            # OSError: sin red / timeout. El resto: respuesta con forma inesperada.
            log.warning("No se pudo consultar el tiempo: %r", e)
            return Respuesta("Lo siento, no puedo consultar el tiempo en este momento.")

        descripcion = DESCRIPCION_WMO.get(codigo)
        if descripcion is None:
            return Respuesta(f"Hace {temperatura} grados.")
        return Respuesta(f"Hace {temperatura} grados, {descripcion}.")

