"""Experimento de la fase 5: ¿qué LLM local elige bien tus skills como tools?

No forma parte del asistente. Requiere Ollama instalado y los modelos
descargados (`ollama pull qwen3.5:2b`). Ejecuta desde la raíz del proyecto:

    python experimentos/probar_ollama.py qwen3.5:2b
    python experimentos/probar_ollama.py qwen3.5:2b llama3.2:3b   # comparar

Para cada modelo mide:
  - carga y VRAM (si size_vram < size, parte del modelo está en la CPU: lento)
  - qué tool elige (o ninguna) para frases que tu router por regex NO entiende
  - con qué argumentos ("cinco minutos" → cantidad=5, unidad=minuto)
  - latencia y velocidad (tokens/s)
"""
from __future__ import annotations

import sys
import time

import ollama

# Tus skills descritas como tools (JSON Schema). Es lo que el contrato Skill
# tendrá que poder generar solo en la integración.
TOOLS = [
    {"type": "function", "function": {
        "name": "hora",
        "description": "Dice la hora actual.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "temporizador",
        "description": "Pone un temporizador que avisa cuando pasa el tiempo indicado.",
        "parameters": {
            "type": "object",
            "properties": {
                "cantidad": {"type": "integer", "description": "Cuántas unidades de tiempo"},
                "unidad": {"type": "string", "enum": ["segundo", "minuto", "hora"]},
            },
            "required": ["cantidad", "unidad"],
        },
    }},
    {"type": "function", "function": {
        "name": "tiempo",
        "description": "Dice el tiempo meteorológico actual: temperatura y si llueve.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "chiste",
        "description": "Cuenta un chiste corto.",
        "parameters": {"type": "object", "properties": {}},
    }},
]

SISTEMA = (
    "Eres Numa, un asistente de voz en español. Responde siempre en español, "
    "en una o dos frases cortas: lo que digas se leerá en voz alta. "
    "Usa una herramienta solo si hace falta para responder."
)

# (frase, tool esperada o None). Ninguna encaja con las regex de tu router.
CASOS = [
    ("¿Me pones un temporizador de cinco minutos?", "temporizador"),
    ("Avísame dentro de media hora", "temporizador"),
    ("¿Necesito paraguas hoy?", "tiempo"),
    ("Hazme reír un poco", "chiste"),
    ("¿Llego tarde si son menos cuarto?", "hora"),
    ("¿Cuál es la capital de Portugal?", None),
    ("Gracias, eres muy maja", None),
]


def chat(modelo: str, frase: str):
    mensajes = [{"role": "system", "content": SISTEMA}, {"role": "user", "content": frase}]
    try:
        # think=False: sin "pensar en voz alta" (añade segundos de latencia).
        return ollama.chat(model=modelo, messages=mensajes, tools=TOOLS, think=False)
    except ollama.ResponseError as e:
        if "think" not in str(e).lower():
            raise
        return ollama.chat(model=modelo, messages=mensajes, tools=TOOLS)  # no soporta think


def probar(modelo: str) -> None:
    print(f"\n══════ {modelo} ══════")
    t0 = time.perf_counter()
    ollama.chat(model=modelo, messages=[{"role": "user", "content": "hola"}],
                keep_alive="10m")  # la primera llamada carga el modelo en la GPU
    print(f"Carga + primera respuesta: {time.perf_counter() - t0:.1f} s")
    for m in ollama.ps().models:
        if m.model.startswith(modelo):
            en_gpu = m.size_vram / m.size * 100
            print(f"Tamaño {m.size / 2**30:.2f} GiB · en GPU {m.size_vram / 2**30:.2f} GiB "
                  f"({en_gpu:.0f} %) · contexto {m.context_length}")

    aciertos = 0
    for frase, esperada in CASOS:
        t0 = time.perf_counter()
        r = chat(modelo, frase)
        ms = (time.perf_counter() - t0) * 1000
        llamadas = r.message.tool_calls or []
        elegida = llamadas[0].function.name if llamadas else None
        ok = elegida == esperada
        aciertos += ok
        velocidad = r.eval_count / (r.eval_duration / 1e9) if r.eval_duration else 0
        detalle = (f"{elegida}({dict(llamadas[0].function.arguments)})" if llamadas
                   else f"texto: {(r.message.content or '').strip()[:70]!r}")
        print(f"{'✅' if ok else '❌'} {ms:5.0f} ms · {velocidad:4.0f} tok/s · {frase!r}\n"
              f"      → {detalle}")
    print(f"Aciertos: {aciertos}/{len(CASOS)}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    modelos = sys.argv[1:] or ["qwen3.5:2b"]
    for modelo in modelos:
        probar(modelo)
        ollama.generate(model=modelo, prompt="", keep_alive=0)  # libera la VRAM


if __name__ == "__main__":
    main()
