"""Tests de la fase 1. Ejecuta con:  python -m pytest

Algunos fallarán al principio a propósito: son tus TODO(human).
Cuando pasen todos, la fase 1 está terminada.
"""
import random
from datetime import datetime

import pytest

from asistente.estado import Estado, MaquinaEstados, TransicionInvalida
from asistente.router import Router, normalizar
from asistente.skills import cargar_skills
from asistente.skills.base import Peticion
from asistente.skills.chiste import ChisteSkill
from asistente.skills.hora import HoraSkill
from asistente.skills.temporizador import TemporizadorSkill
from asistente.skills.tiempo import TiempoSkill


# --- Router ---------------------------------------------------------------

def test_normalizar_quita_tildes_y_signos():
    assert normalizar("¿Qué HORA es?") == "que hora es"


@pytest.mark.parametrize(
    "frase, skill",
    [
        ("¿Qué hora es?", "hora"),
        ("Pon un temporizador de 5 minutos", "temporizador"),
        ("¿Qué tiempo hace?", "tiempo"),
        ("Cuéntame un chiste", "chiste"),
    ],
)
def test_router_elige_skill(frase, skill):
    resultado = Router(cargar_skills()).resolver(frase)
    assert resultado is not None and resultado[0].nombre == skill


def test_router_extrae_entidades():
    _, peticion = Router(cargar_skills()).resolver("temporizador de 10 segundos")
    assert peticion.entidades == {"cantidad": "10", "unidad": "segundo"}


def test_router_sin_coincidencia():
    assert Router(cargar_skills()).resolver("enciende la luz del salón") is None


# --- Máquina de estados ---------------------------------------------------

def test_transicion_valida():
    m = MaquinaEstados()
    m.transicionar(Estado.PENSANDO)
    assert m.estado is Estado.PENSANDO


def test_transicion_invalida():  # TODO(human) en estado.py
    m = MaquinaEstados()
    with pytest.raises(TransicionInvalida):
        m.transicionar(Estado.HABLANDO)  # de REPOSO no se puede hablar directamente


# --- Skills ---------------------------------------------------------------

def test_hora():
    skill = HoraSkill(ahora=lambda: datetime(2026, 1, 1, 9, 5))
    assert skill.ejecutar(Peticion("que hora es")).texto == "Son las 9:05."


def test_temporizador_confirma_y_avisa():  # TODO(human) en temporizador.py
    avisos = []
    skill = TemporizadorSkill(avisar=avisos.append)
    r = skill.ejecutar(Peticion("", {"cantidad": "1", "unidad": "segundo"}))
    assert "1 segundo" in r.texto
    import time
    time.sleep(1.3)
    assert avisos, "El temporizador debería haber avisado"


def test_tiempo_con_datos_falsos():  # TODO(human) en tiempo.py
    falso = lambda url: {"current": {"temperature_2m": 18.4, "weather_code": 3}}
    r = TiempoSkill(obtener=falso).ejecutar(Peticion("que tiempo hace"))
    assert "18" in r.texto and "nublado" in r.texto


def test_tiempo_sin_red_no_revienta():  # TODO(human) en tiempo.py
    def sin_red(url):
        raise OSError("sin conexión")
    r = TiempoSkill(obtener=sin_red).ejecutar(Peticion("que tiempo hace"))
    assert r.texto  # responde algo, en vez de lanzar la excepción


def test_chiste_es_de_la_lista():
    skill = ChisteSkill(chistes=("a", "b", "c"), aleatorio=random.Random(0))
    assert skill.ejecutar(Peticion("chiste")).texto in {"a", "b", "c"}


def test_chiste_no_repite_seguidos():
    skill = ChisteSkill(chistes=("a", "b"), aleatorio=random.Random(0))
    textos = [skill.ejecutar(Peticion("chiste")).texto for _ in range(20)]
    assert all(x != y for x, y in zip(textos, textos[1:]))


def test_chiste_con_un_solo_chiste():
    skill = ChisteSkill(chistes=("unico",))
    assert [skill.ejecutar(Peticion("chiste")).texto for _ in range(3)] == ["unico"] * 3


def test_chiste_con_duplicados_no_se_cuelga():
    # Regresión: con "repetir el sorteo mientras salga el último", una lista
    # con duplicados (len > 1 pero un solo valor distinto) era un bucle infinito.
    skill = ChisteSkill(chistes=("igual", "igual"))
    assert [skill.ejecutar(Peticion("chiste")).texto for _ in range(3)] == ["igual"] * 3
