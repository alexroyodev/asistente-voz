# ADR 0001: Construir el núcleo propio en Python

- **Estado:** aceptada
- **Fecha:** 2026-10-30

## Contexto

Quiero un asistente de voz estilo Alexa como proyecto de aprendizaje. Existen
soluciones completas de código abierto (Home Assistant Assist, OpenVoiceOS)
que funcionarían antes, pero esconden justo lo que quiero aprender.

## Decisión

Escribir yo el núcleo (máquina de estados, router, sistema de skills,
orquestación) y usar como librerías las piezas especializadas: openWakeWord,
faster-whisper, Silero VAD, Piper y un LLM local vía Ollama.

Lenguaje: Python, porque todas esas piezas tienen buen soporte en él.

## Alternativas consideradas

- **Home Assistant Assist:** muy maduro y orientado a domótica; aprendería
  configuración, no arquitectura.
- **OpenVoiceOS:** buena arquitectura modular para estudiar; la usaré como
  referencia de diseño, no como base.
- **Implementar también STT/TTS/wake word:** fuera de alcance; son problemas
  de machine learning distintos.

## Consecuencias

- Más trabajo y resultado menos pulido al principio.
- Cada pieza externa queda detrás de una interfaz mía para poder cambiarla.
- Más adelante podré hablar el protocolo Wyoming para reutilizar servicios.
