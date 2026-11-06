"""Cerebro (fase 5): un LLM local elige skill cuando ninguna regex encaja.

No usa "tool calling": con modelos pequeños, obligar a ELEGIR de una lista
cerrada (salida estructurada con JSON Schema) acierta mucho más (10/10 frente
a 5/7 en experimentos/probar_ollama.py). Ver ADR 0006.

Todo se genera a partir del contrato Skill (nombre + descripcion + parametros):
añadir una skill no obliga a tocar este archivo.

    ClienteLLM  ← solo habla con Ollama (clasificar / charlar)
      ├── Cerebro         elige skill cuando la regex no encaja
      └── ConversarSkill  redacta respuestas libres ("Es Lisboa")
"""
from __future__ import annotations

import json
import logging
from typing import Any, Iterable, Iterator

from asistente.skills.base import Peticion, Skill

log = logging.getLogger(__name__)

MODELO_POR_DEFECTO = "llama3.2:3b"
NUM_CTX = 2048  # con 4096 la caché no deja que el modelo quepa entero en la GPU


class ClienteLLM:
    """Envoltorio mínimo de Ollama: lo único de este archivo que habla con él."""

    def __init__(self, modelo: str = MODELO_POR_DEFECTO, cliente=None) -> None:
        if cliente is None:
            import ollama  # aquí: sin Ollama instalado, el resto del módulo funciona
            cliente = ollama.Client()
        self._cliente = cliente
        self.modelo = modelo

    def _chat(self, sistema: str, texto: str, **extra) -> str:
        respuesta = self._cliente.chat(
            model=self.modelo,
            messages=[{"role": "system", "content": sistema},
                      {"role": "user", "content": texto}],
            options={"num_ctx": NUM_CTX, **extra.pop("options", {})},
            keep_alive=-1,  # que no se descargue de la GPU tras 5 min sin uso
            **extra,
        )
        return respuesta.message.content or ""

    def precargar(self) -> None:
        """Carga el modelo en la GPU ya (~6 s), no en la primera pregunta."""
        self._chat("Responde 'ok'.", "hola")

    def descargar(self) -> None:
        """Libera la VRAM. Ollama es un servidor APARTE: sigue vivo cuando el
        asistente termina, y con keep_alive=-1 retendría el modelo para siempre."""
        try:
            self._cliente.generate(model=self.modelo, prompt="", keep_alive=0)
        except Exception as e:
            log.warning("No he podido descargar el LLM: %r", e)

    def clasificar(self, sistema: str, esquema: dict, texto: str) -> dict:
        """Respuesta obligada por un JSON Schema. Temperatura 0: siempre lo mismo."""
        return json.loads(self._chat(sistema, texto, format=esquema,
                                     options={"temperature": 0}))

    def charlar(self, sistema: str, texto: str) -> str:
        return self._chat(sistema, texto).strip()

    def charlar_en_flujo(self, sistema: str, texto: str,
                         historial: Iterable[dict] = ()) -> Iterator[str]:
        """Como charlar(), pero entrega cada token en cuanto Ollama lo genera.

        Es un generador perezoso: la petición no sale hasta el primer next().
        Al cerrarlo (close(), p. ej. tras una interrupción), se cierra la
        conexión y Ollama deja de generar. `historial`: turnos anteriores en
        formato chat (memoria corta, ADR 0009), entre el sistema y la frase.
        """
        flujo = self._cliente.chat(
            model=self.modelo,
            messages=[{"role": "system", "content": sistema}, *historial,
                      {"role": "user", "content": texto}],
            options={"num_ctx": NUM_CTX}, keep_alive=-1, stream=True,
        )
        try:
            for trozo in flujo:
                yield trozo.message.content or ""
        finally:
            cerrar = getattr(flujo, "close", None)
            if cerrar is not None:
                cerrar()


class Cerebro:
    """Elige skill con el LLM. Misma salida que Router.resolver(): encaja en su hueco."""

    def __init__(self, llm: ClienteLLM, skills: Iterable[Skill]) -> None:
        self._llm = llm
        self._skills = list(skills)
        # Se generan una vez: las skills no cambian mientras corre el asistente.
        self._esquema = construir_esquema(self._skills)
        self._instrucciones = {
            False: construir_instrucciones(self._skills, hay_contexto=False),
            True: construir_instrucciones(self._skills, hay_contexto=True),
        }

    def resolver(self, texto: str, contexto: str = "") -> tuple[Skill, Peticion] | None:
        """`contexto`: la conversación reciente en texto plano (ADR 0009).

        Va DENTRO del mensaje, no como turnos de chat: si el clasificador
        viera respuestas de "assistant" en lenguaje natural, se le estaría
        enseñando a responder con frases en vez de con el JSON pedido.
        """
        try:
            datos = self._llm.clasificar(self._instrucciones[bool(contexto)], self._esquema,
                                         con_contexto(texto, contexto))
        except Exception as e:  # Ollama caído, JSON roto...: seguimos sin LLM
            log.warning("El LLM no ha podido clasificar %r: %r", texto, e)
            return None
        log.debug("LLM: %r → %r", texto, datos)
        return validar(datos, self._skills, texto)


def con_contexto(texto: str, contexto: str) -> str:
    """La petición, precedida de la conversación reciente si la hay."""
    if not contexto:
        return texto
    return f"Conversación reciente:\n{contexto}\n\nPetición actual: {texto}"


def construir_esquema(skills: Iterable[Skill]) -> dict:
    """JSON Schema que obliga al LLM a responder {"intencion": ..., <parámetros>}.

    Todos los parámetros de todas las skills aparecen, admitiendo null: el
    LLM rellena solo los de la skill que elige. Ollama garantiza que la
    respuesta encaja con el esquema (no puede inventarse una intención).
    """
    skills = list(skills)
    propiedades: dict[str, dict] = {
        "intencion": {"type": "string", "enum": [s.nombre for s in skills]},
    }
    for skill in skills:
        for nombre, esquema in skill.parametros.items():
            propiedades[nombre] = _admitir_null(esquema)
    return {"type": "object", "properties": propiedades, "required": list(propiedades)}


def _admitir_null(esquema: dict) -> dict:
    tipo = esquema.get("type", "string")
    resultado = {**esquema, "type": [tipo, "null"]}
    if "enum" in esquema:
        resultado["enum"] = [*esquema["enum"], None]
    return resultado


def construir_instrucciones(skills: Iterable[Skill], hay_contexto: bool = False) -> str:
    """El mensaje de sistema: qué es cada intención, sacado de las descripciones.

    Con `hay_contexto`, se añade la `pista_contexto` de cada skill ("otro
    igual" → copia los parámetros). Sin conversación previa no aparece, y
    así el modelo no se inventa un temporizador para "pon otro igual".
    """
    lineas = ["Clasifica la petición del usuario a un asistente de voz en una intención."]
    for skill in skills:
        pista = f" {skill.pista_contexto}" if hay_contexto and skill.pista_contexto else ""
        lineas.append(f"- {skill.nombre}: {skill.descripcion}{pista}")
    lineas.append("Rellena solo los parámetros de la intención elegida; el resto, null.")
    lineas.append("Si la petición se refiere a la conversación reciente ('otro igual', "
                  "'y eso', '¿y él?'), usa esa conversación para elegir la intención "
                  "y rellenar los parámetros.")
    return "\n".join(lineas)


def validar(datos: dict[str, Any], skills: Iterable[Skill],
            texto: str) -> tuple[Skill, Peticion] | None:
    """Convierte la respuesta del LLM en (skill, peticion), o None si no vale.

    Aunque Ollama obligue al esquema, NO nos fiamos: lo que genera un LLM se
    valida como si viniera de un formulario web. Si falta un parámetro
    obligatorio, mejor "no sé hacer eso" que ejecutar la skill con basura.
    """
    por_nombre = {s.nombre: s for s in skills}
    skill = por_nombre.get(datos.get("intencion"))
    if skill is None:
        return None
    entidades: dict[str, str] = {}
    for nombre, esquema in skill.parametros.items():
        valor = datos.get(nombre)
        if valor is None or ("enum" in esquema and valor not in esquema["enum"]):
            return None
        if esquema.get("type") == "integer":
            # bool es subclase de int en Python: isinstance(True, int) es True.
            if isinstance(valor, bool) or not isinstance(valor, int) \
                    or valor < esquema.get("minimum", valor):
                return None
        entidades[nombre] = str(valor)  # como las de la regex: siempre texto
    return skill, Peticion(texto=texto, entidades=entidades)
