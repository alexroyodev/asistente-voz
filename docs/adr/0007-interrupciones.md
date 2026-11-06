# ADR 0007: Interrumpir a Numa mientras habla ("Oye Numa, para")

- **Estado:** propuesta
- **Fecha:** 2026-11-04

## Contexto

Mientras Numa habla, el hilo principal está bloqueado dentro de
`voz.decir()` y el detector de activación (ADR 0005) está en pausa para no
oír a Piper. Para interrumpir hay que escuchar MIENTRAS Piper suena, y:

- El VAD no sirve para cortar frases: con Piper hablando nunca hay silencio.
- Con audio débil, la pista `hotwords="Oye Numa"` hace que Whisper alucine
  la propia pista (2/16 ventanas con la voz de Piper grabada; 4/16 con
  `vad_filter`). Sin pista, tu "Oye Numa" a secas no se reconoce.
- Medido en este portátil: Piper llega al micro con un pico de ~0,003 RMS
  (el micro Realtek parece atenuar sus propios altavoces) y tu voz con
  ~0,12. Con puerta de volumen: 0 falsos positivos en 25 s y detección a la
  primera, cortando a Piper ~1-2,5 s después.

## Decisión

- Un **segundo detector** (`asistente/interrupcion.py`), en su propio hilo
  y con su propia grabación, activo solo en `HABLANDO` (Event `hablando`,
  que el principal activa alrededor de cada `voz.decir()` interrumpible).
- Cada **0,75 s** mira la ventana de los **últimos 2 s**. Solo la
  transcribe si su **pico de volumen** (RMS del tramo de 100 ms más
  fuerte) supera **0,005**: Piper no llega, tu voz sí (y se ahorra GPU).
- Si oye "numa", **este hilo llama a `voz.parar()`** (diseñado en el
  ADR 0002 para llamarse desde otro hilo) y publica:
  - "Oye Numa, para / cállate / silencio / basta…" → nada (solo callar).
  - Cualquier otra cosa → `Activar()`: pita y escucha. La orden NO se usa:
    la ventana puede haberla cortado a medias ("Oye Numa, qué").
- Las **órdenes de callar** (frases de 1-2 palabras que empiezan por "para",
  "cállate", "silencio", "basta"…) no se responden **nunca**, lleguen como
  lleguen: en la misma ventana que "Oye Numa", tras el bip, o como
  "Oye Numa, para" en `REPOSO`. Probado: con una pausa entre "Oye Numa" y
  "para", el "para" llegaba tras el bip y el LLM se ponía a charlar.
- Tras cortar, `decir()` vuelve antes y el bucle sigue por su camino
  normal: `HABLANDO → REPOSO → (evento)`. Sin transiciones nuevas.
- **Periodo refractario** de 2 s tras cortar: las ventanas solapadas
  volverían a oír el final de tu frase e interrumpirían la respuesta.

## Alternativas consideradas

- **`decir()` no bloqueante** y que el principal llame a `parar()`: más
  puro, pero cambia el contrato `Voz` y gran parte del bucle.
- **Usar la flecha ⑨ `HABLANDO → ESCUCHANDO`**: más fiel al dibujo, pero
  requiere que `decir()` informe del corte y otra transición más.
- **Un solo detector con dos modos:** mezclaría dos lógicas distintas
  (silencios frente a ventanas) con `if modo == …`.
- **Cancelación de eco (AEC):** lo correcto en general, pero innecesario
  con este hardware (el micro ya atenúa los altavoces).
- **Atender "Oye Numa, <orden>" también al interrumpir:** la orden puede
  llegar cortada por la ventana.

## Consecuencias

- Se puede cortar cualquier respuesta o aviso diciendo "Oye Numa".
- Latencia del corte ~0,8-1,6 s (paso de 0,75 s + ~0,6-0,85 s de Whisper).
- El umbral depende del hardware y del volumen de los altavoces: con otros
  altavoces o en la Raspberry (fase 7) hay que recalibrarlo con
  `experimentos/probar_interrupcion.py`.
- Tres grabaciones del micro a la vez (activación, interrupción y
  `OidoWhisper`): bien con MME en Windows.
- "Silencio, por favor" (3 palabras) no cuenta como callar; "para qué
  sirve…" tampoco (bien). Palabras sueltas mal transcritas ("Para" →
  "Fuma") pueden acabar en el LLM.
- La flecha ⑨ de la máquina de estados sigue sin usarse.
- Con openWakeWord (paso B de la fase 4) la detección sería en streaming,
  sin ventanas ni puerta de volumen: más rápida y sin cortar órdenes.
