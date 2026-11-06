# ADR 0005: Activación por voz "Oye Numa" con VAD + Whisper (provisional)

- **Estado:** aceptada
- **Fecha:** 2026-11-04

## Contexto

La fase 4 quiere activar el asistente con la voz en vez del Enter. La
palabra elegida es en español, "Numa". openWakeWord, la opción prevista,
solo soporta inglés (sus datos de entrenamiento salen de un TTS inglés) y
entrena solo en Linux. Además, "Numa" (2 sílabas) se parece a palabras
comunes: "una", "luna", "nunca", "ninguna", "suma".

Medidas propias (experimento con turbo + `hotwords`): "Oye Numa" detectado
7/7; "Oye Numa, <orden>" separa bien la orden; "¿Qué tiempo hace?" no
activa. Sin `hotwords`, "Oye Numa" a secas sale "¿O tiene número?".

## Decisión

- Frase de activación: **"Oye Numa"** (4 sílabas, más robusta).
- **Paso A (este ADR):** detector provisional con VAD + Whisper en un hilo
  productor (`asistente/activacion.py`): segmenta el audio continuo con
  Silero (0,5 s de silencio), transcribe con el MISMO modelo que
  `OidoWhisper` y `hotwords="Oye Numa"`, y busca "numa" como palabra entera.
  - "Oye Numa" a secas → `Activar()`: el asistente pita y escucha la orden.
  - "Oye Numa, <orden>" → `Frase(orden)`: directo al router, sin otro turno.
- El detector **solo escucha en `REPOSO`**: el hilo principal le da paso con
  un `threading.Event` (`set` al esperar evento, `clear` al atenderlo). Lo
  comprueba al segmentar y otra vez antes de publicar (check-then-act).
- Enter y "Oye Numa" conviven: dos productores del mismo `Activar()`.
  `--sin-numa` desactiva el detector.
- Nuevo método opcional `Voz.pitar()` (bloqueante) para el "te escucho".
- Si el detector falla, se registra y el asistente sigue con Enter (no
  publica `Salir()`, a diferencia del hilo de entrada).
- **Paso B (pendiente):** modelo openWakeWord para "Oye Numa", entrenado en
  Colab con pronunciación aproximada en inglés; publicará el mismo evento.

## Alternativas consideradas

- **openWakeWord directamente:** sin poder probar la fase 4 hasta entrenar;
  y la calidad para una palabra española es incierta.
- **Picovoice Porcupine:** soporta español, pero es cerrado, requiere
  cuenta y licencia personal; se aprende menos.
- **"Numa" a secas:** más cómodo, más falsos positivos.
- **Siempre `Activar()`:** obligaría a repetir la orden tras la activación.
- **Detector siempre escuchando y filtrar en el principal:** transcribiría
  también la voz de Piper (GPU) y llenaría la cola de eventos inútiles.
- **Una segunda instancia de Whisper para el detector:** doble de VRAM.

## Consecuencias

- "Oye Numa, ¿qué hora es?" se responde en un solo turno (ventaja que
  openWakeWord no tendrá: solo detecta, no transcribe).
- Whisper transcribe TODO lo que se habla en la habitación mientras está en
  `REPOSO`: uso continuo de GPU, y cada activación tarda ~0,5 s de silencio
  + ~0,6 s de transcripción.
- Falsos positivos con conversación o tele: sin medir todavía.
- Dos grabaciones simultáneas del micrófono (detector + `OidoWhisper`):
  funciona con MME en Windows; en Linux/Raspberry (fase 7) habrá que verlo.
- Un "Oye Numa" transcrito justo cuando se pulsa Enter se descarta.
