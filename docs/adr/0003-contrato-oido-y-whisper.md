# ADR 0003: Entrada de voz detrás de un contrato `Oido`, con faster-whisper

- **Estado:** aceptada
- **Fecha:** 2026-11-03

## Contexto

En la fase 3 el asistente pasa de leer el teclado a escuchar el micrófono
("pulsar para hablar"). Whisper puede equivocarse con habla rápida y puede
inventar texto ("alucinar") con silencio o ruido. La VRAM (4 GB) tiene que
dejar sitio para el LLM de la fase 5.

Medidas propias (RTX 3050 Ti, int8_float16, frases de 2-4 s):

| Modelo | VRAM | Latencia | Habla rápida |
|---|---|---|---|
| small | ~335 MiB | 340-470 ms | falla ("cuándo" por "cuéntame un chiste") |
| turbo (large-v3-turbo) | ~880 MiB | 560-730 ms | bien (1 de 2 exacta; la otra, válida para el router) |

## Decisión

El núcleo solo conoce una clase abstracta `Oido` (`asistente/oido.py`):

- `escuchar() -> str | None`: **bloquea** hasta tener una frase. `None`
  significa "no se entendió nada": el bucle vuelve a `REPOSO` sin responder.
- `OidoTeclado` (como la fase 1) y `OidoWhisper`.
- `OidoWhisper`: Enter empieza; el **fin de frase lo decide Silero VAD**
  (~0,8 s de silencio tras haber hablado), usando el modelo ONNX que trae
  faster-whisper (sin PyTorch). Límites: 5 s sin hablar → `None`; 15 s → corte.
- Contra alucinaciones, tres capas: audio < 0,3 s → `None`; `vad_filter=True`;
  descartar segmentos con `no_speech_prob >= 0,6`.
- Modelo **configurable** (`--whisper small`), `turbo` por defecto.
- Entrada y salida se eligen por separado: `--teclado`, `--texto`.

## Alternativas consideradas

- **Cadena vacía o excepción en vez de `None`:** "" se confunde fácil; no
  entender es normal en voz, no excepcional.
- **Enter para parar / mantener una tecla:** más simple / más natural, pero
  el VAD ensaya ya el fin de frase automático que necesitará la fase 4.
  Mantener tecla requiere librerías de teclado global.
- **Paquete `silero-vad`:** depende de PyTorch (~2 GB). El de faster-whisper basta.
- **`small` fijo:** menos VRAM y latencia, pero falla con habla rápida.
  Alternativa pendiente de probar: `small` + `initial_prompt` con vocabulario.
- **Un solo modo `--texto`:** impedía probar Whisper sin Piper o al revés.

## Consecuencias

- La máquina de estados se recorre completa por primera vez:
  `REPOSO → ESCUCHANDO → PENSANDO → HABLANDO → REPOSO`.
- Latencia percibida ≈ 0,8 s (silencio de fin) + transcripción (~0,6 s con
  turbo) + router/skill + primer audio de Piper (~0,08 s). El silencio de
  fin es ahora el mayor sumando: bajarlo acelera, pero corta a quien hace pausas.
- El VAD se reevalúa sobre todo lo grabado cada 100 ms (el modelo no guarda
  estado entre llamadas): coste ~4 ms por 2,4 s de audio, despreciable para
  frases cortas.
- Las DLL de CUDA vienen de `pip` y se registran con `os.add_dll_directory`.
  Sin GPU, `OidoWhisper` falla al arrancar (queda abierto un modo CPU).
- Con `turbo`, Whisper + LLM en 4 GB irá justo: se revisará en la fase 5.
- Mientras se espera el Enter, el estado ya es `ESCUCHANDO`.
