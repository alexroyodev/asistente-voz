"""Tests del cerebro: sin Ollama (un cliente falso devuelve respuestas fijas)."""
import json
from types import SimpleNamespace

import pytest

from asistente.cerebro import (
    Cerebro, ClienteLLM, construir_esquema, construir_instrucciones, validar,
)
from asistente.skills import cargar_skills
from asistente.skills.base import Peticion
from asistente.skills.conversar import ConversarSkill
from asistente.skills.temporizador import TemporizadorSkill

SKILLS = cargar_skills()


class OllamaFalso:
    """Imita ollama.Client().chat(): devuelve `contenido` y apunta las llamadas."""

    def __init__(self, contenido="", error=None):
        self.contenido, self.error, self.llamadas = contenido, error, []

    def chat(self, **kwargs):
        self.llamadas.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(message=SimpleNamespace(content=self.contenido))


def cerebro_con(respuesta: dict | str, error=None):
    contenido = respuesta if isinstance(respuesta, str) else json.dumps(respuesta)
    falso = OllamaFalso(contenido, error)
    skills = cargar_skills(charlar_en_flujo=lambda s, t: iter(["¡De", " na", "da!"]))
    return Cerebro(ClienteLLM("falso", cliente=falso), skills), falso


def test_cerebro_elige_skill_y_extrae_entidades():
    cerebro, falso = cerebro_con({"intencion": "temporizador", "cantidad": 30,
                                  "unidad": "minuto"})
    skill, peticion = cerebro.resolver("avísame en media hora")
    assert skill.nombre == "temporizador"
    assert peticion.entidades == {"cantidad": "30", "unidad": "minuto"}
    pedido = falso.llamadas[0]
    assert pedido["format"]["properties"]["intencion"]["enum"][-1] == "conversar"
    assert pedido["options"] == {"num_ctx": 2048, "temperature": 0}


def test_cerebro_puede_elegir_conversar():
    cerebro, _ = cerebro_con({"intencion": "conversar", "cantidad": None, "unidad": None})
    skill, peticion = cerebro.resolver("gracias, Numa")
    assert isinstance(skill, ConversarSkill)
    assert list(skill.ejecutar(peticion).frases) == ["¡De nada!"]  # tokens → frase


@pytest.mark.parametrize("respuesta, error", [
    ("esto no es JSON", None),
    ({}, ConnectionError("Ollama no está en marcha")),
])
def test_cerebro_si_falla_el_llm_devuelve_none(respuesta, error):
    cerebro, _ = cerebro_con(respuesta, error)
    assert cerebro.resolver("lo que sea") is None


def frases_de(tokens_o_error):
    """Ejecuta ConversarSkill con un 'LLM' que es un generador (como el real)."""
    def llm(sistema, texto):
        for t in tokens_o_error:
            if isinstance(t, Exception):
                raise t
            yield t
    return list(ConversarSkill(llm).ejecutar(Peticion("hola")).frases)


def test_conversar_si_el_llm_falla_antes_de_hablar_se_disculpa():
    assert frases_de([ConnectionError()]) == ["Ahora mismo no puedo pensar en eso, perdona."]


def test_conversar_si_el_llm_falla_a_mitad_avisa():
    frases = frases_de(["Roma se fundó en el 753. ", "Rómulo", ConnectionError()])
    assert frases[0] == "Roma se fundó en el 753."
    assert frases[-1].endswith("Perdona, me he perdido.")


def test_conversar_si_el_llm_no_dice_nada():
    assert frases_de([" ", ""]) == ["No sé qué decirte a eso."]


def test_cerrar_el_flujo_cierra_el_del_llm():
    # Tras una interrupción, hablar() cierra las frases: el cierre debe llegar
    # hasta el generador del LLM (que es quien cierra la conexión con Ollama).
    cerrado = []

    def llm(sistema, texto):
        try:
            yield from ["Primera frase larga. ", "Segunda frase. ", "Tercera."]
        finally:
            cerrado.append(True)

    frases = ConversarSkill(llm).ejecutar(Peticion("hola")).frases
    assert next(frases) == "Primera frase larga."
    frases.close()                      # ← lo que hace hablar() al interrumpir
    assert cerrado == [True]


def test_conversar_no_llama_al_llm_hasta_pedir_la_primera_frase():
    llamadas = []

    def llm(sistema, texto):
        llamadas.append(texto)
        yield "Hola."

    respuesta = ConversarSkill(llm).ejecutar(Peticion("hola"))
    assert llamadas == []               # perezoso: aún no se ha pedido nada
    list(respuesta.frases)
    assert llamadas == ["hola"]


def test_sin_llm_no_hay_conversar():
    assert "conversar" not in [s.nombre for s in cargar_skills()]


def test_esquema_lista_todas_las_skills_como_intencion():
    esquema = construir_esquema(SKILLS)
    assert esquema["properties"]["intencion"]["enum"] == [s.nombre for s in SKILLS]


def test_esquema_incluye_parametros_que_admiten_null():
    props = construir_esquema(SKILLS)["properties"]
    assert props["cantidad"]["type"] == ["integer", "null"]
    assert props["unidad"]["enum"] == ["segundo", "minuto", "hora", None]
    assert set(construir_esquema(SKILLS)["required"]) == set(props)


def test_instrucciones_usan_las_descripciones():
    texto = construir_instrucciones(SKILLS)
    for skill in SKILLS:
        assert f"- {skill.nombre}: {skill.descripcion}" in texto


def test_validar_temporizador_convierte_a_texto():
    skill, peticion = validar({"intencion": "temporizador", "cantidad": 5, "unidad": "minuto"},
                              SKILLS, "avísame en cinco minutos")
    assert isinstance(skill, TemporizadorSkill)
    assert peticion.entidades == {"cantidad": "5", "unidad": "minuto"}  # como la regex
    assert peticion.texto == "avísame en cinco minutos"


def test_validar_skill_sin_parametros_ignora_los_demas():
    skill, peticion = validar({"intencion": "hora", "cantidad": None, "unidad": None},
                              SKILLS, "¿llego tarde?")
    assert skill.nombre == "hora" and peticion.entidades == {}


@pytest.mark.parametrize("datos", [
    {"intencion": "inventada"},                                          # no existe
    {"intencion": "temporizador", "cantidad": None, "unidad": "minuto"},  # falta cantidad
    {"intencion": "temporizador", "cantidad": 5, "unidad": "semana"},     # fuera del enum
    {"intencion": "temporizador", "cantidad": "5", "unidad": "minuto"},   # texto, no entero
    {"intencion": "temporizador", "cantidad": 0, "unidad": "minuto"},     # menor que minimum
    {"intencion": "temporizador", "cantidad": True, "unidad": "minuto"},  # bool no es número
    {},
])
def test_validar_rechaza_basura(datos):
    assert validar(datos, SKILLS, "x") is None
