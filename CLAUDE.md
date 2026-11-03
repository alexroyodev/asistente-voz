# Proyecto: asistente de voz propio (estilo Alexa)

Este es un proyecto de APRENDIZAJE. El objetivo principal es que yo entienda y
construya el núcleo del asistente; que funcione es secundario.

## Cómo quiero que me ayudes

- No escribas por mí el núcleo: máquina de estados (`asistente/estado.py`),
  router (`asistente/router.py`), contrato de skills (`asistente/skills/base.py`)
  y, más adelante, el bucle de audio y el orquestador del LLM. Ahí guíame con
  preguntas, pistas y revisión de mi código.
- Si un `TODO(human)` está en el código, es mío. No lo resuelvas aunque te lo
  pida de pasada; dame una pista y pregúntame si de verdad quiero la solución.
- Puedes escribir libremente: tests, scripts de instalación, configuración,
  código de pegamento aburrido (lectura de config, logging) y ejemplos de
  cómo usar una librería nueva fuera del proyecto.
- Cuando revises mi código, señala bugs y riesgos, y explica el porqué.
- Al introducir una tecnología nueva (VAD, Whisper, Piper, openWakeWord,
  Ollama…), explícame primero el concepto en 3-5 frases.
- Responde en español.

## Entorno

- Windows 11, Python 3.11+ en un entorno virtual (`.venv`).
- GPU NVIDIA RTX 3050 Ti (portátil, 4 GB de VRAM): tenlo en cuenta al
  proponer tamaños de modelo.
- Tests: `python -m pytest`. Ejecutar: `python -m asistente -v`.

## Documentación

- Diario en `docs/diario.md`; decisiones de arquitectura en `docs/adr/`.
- Al terminar una sesión, recuérdame anotar en el diario qué aprendí y
  propón un ADR si tomamos una decisión importante.

## Fases

1. Modo texto: router + skills (hora, temporizador, tiempo) ← ACTUAL
2. Salida de voz con Piper
3. Entrada de voz con faster-whisper + VAD (pulsar para hablar)
4. Palabra de activación con openWakeWord
5. Cerebro con LLM local (Ollama + tool calling)
6. Pulido: interrupciones, latencia, memoria corta
7. Satélite (Raspberry Pi) + servidor
