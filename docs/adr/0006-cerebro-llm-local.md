# ADR 0006: Cerebro con LLM local: regex primero, LLM con salida estructurada

- **Estado:** aceptada
- **Fecha:** 2026-11-04

## Contexto

El router por regex solo entiende frases que encajan en sus patrones:
"¿Me pones un temporizador de cinco minutos?" (número en palabras),
"¿Necesito paraguas?" o "Gracias" reciben "todavía no sé hacer eso".
Hay 4 GB de VRAM, de los que Whisper turbo usa ~880 MiB.

Experimentos (`experimentos/probar_ollama.py`, 2026-11-04):

| Enfoque | Modelo | En GPU | Latencia | Aciertos |
|---|---|---|---|---|
| Tool calling | qwen3.5:2b | 63-65 % | 0,6-2,5 s | 5/7 · 6/10 |
| Tool calling | llama3.2:3b | 80 → 100 %* | 150-620 ms | 5/7 (abusa de las tools) |
| Tool calling + tool "conversar" | llama3.2:3b | 100 %* | 275-785 ms | 8/10 (deja de usarlas e inventa) |
| **Salida estructurada (enum)** | **llama3.2:3b** | **100 %*** | **330-450 ms** | **10/10** |

\* con `num_ctx=2048` (con 4096 no cabe entero en la GPU).

## Decisión

- **Regex primero, LLM si no encaja.** Las reglas son la vía rápida
  (0 ms, deterministas); el LLM, el respaldo.
- Modelo **llama3.2:3b** en Ollama, `num_ctx=2048`, `temperature=0` para
  clasificar, configurable con `--llm`.
- **Salida estructurada, no tool calling:** un JSON Schema con
  `intencion` (enum de nombres de skill) y los parámetros de todas las
  skills (admitiendo null). El LLM *clasifica*; no decide si actuar.
- El contrato `Skill` gana `parametros` (JSON Schema, mismos nombres que
  los grupos de la regex). Esquema e instrucciones se generan de
  `nombre + descripcion + parametros`: una skill nueva no toca el cerebro.
  Las `descripcion` pasan a estar escritas para el LLM, con ejemplos.
- La salida del LLM **se valida** (`validar`) aunque Ollama obligue al
  esquema; las entidades se convierten a texto, como las de la regex.
  `Cerebro.resolver()` devuelve lo mismo que `Router.resolver()`.
- **`conversar` es una skill más**, sin patrones (solo la elige el LLM);
  una 2ª llamada al LLM redacta la respuesta con instrucciones de
  prudencia (breve, sin emojis, "no estoy seguro" en vez de inventar).
- `ClienteLLM` (habla con Ollama) separado de `Cerebro` (elige skill) y
  de `ConversarSkill` (redacta): orden de creación lineal, sin ciclos.
- **Sin Ollama, el asistente sigue** sin LLM (aviso al arrancar);
  `--sin-llm` para desactivarlo a propósito.
- El modelo se precarga al arrancar (`keep_alive=-1`) y se descarga al
  salir (Ollama es un servidor aparte que lo retendría en la VRAM).

## Alternativas consideradas

- **Siempre el LLM:** +400 ms en todo y dependencia de Ollama.
- **Tool calling:** los modelos pequeños abusan de las tools o, con una
  tool "conversar", dejan de usarlas y se inventan datos.
- **qwen3.5:2b / qwen3:4b:** no caben enteros en la GPU con Whisper.
- **Esquema a mano en un solo sitio:** cada skill nueva tocaría dos sitios.
- **No arrancar sin Ollama:** el asistente es útil sin LLM.

## Consecuencias

- VRAM con todo cargado (Whisper turbo + LLM + detector): ~3,2 GB de 4.
- Las frases que no encajan en las regex tardan ~400-550 ms más en
  `PENSANDO`; `conversar`, una llamada más (~400-800 ms).
- Un 3B sabe poco y se equivoca con seguridad ("una araña tiene seis
  patas"), incluso con instrucciones de prudencia: riesgo asumido.
- El LLM puede devolver parámetros de otra skill (paraguas → `tiempo` con
  `cantidad: 1`): `validar` los ignora.
- Las descripciones de las skills ahora son comportamiento: cambiarlas
  cambia lo que elige el LLM.
