# ADR 0009: Memoria corta de la conversación

- **Estado:** propuesta
- **Fecha:** 2026-11-06

## Contexto

Cada frase era un mundo: "pon otro igual" o "¿y quién fue su primer
emperador?" no tenían sentido para Numa. Un LLM no recuerda entre llamadas:
la "memoria" es reenviarle los turnos anteriores, que ocupan contexto
(`num_ctx=2048`). En la fase 1 se anotó que el estado de conversación no
debe vivir en las skills (varios satélites en la fase 7).

## Decisión

- **`Conversacion`** (`asistente/conversacion.py`): últimos **3 turnos**
  (`deque(maxlen=3)`), que **caducan a los 120 s** sin hablar
  (`time.monotonic`, reloj inyectable). La posee el hilo principal; en la
  fase 7, una por satélite. Las skills siguen sin estado de conversación.
- La caducidad se decide **al empezar el turno** (`empezar_turno()`), nunca
  al anotar: un turno que empezó a los 115 s y usó la memoria no puede
  borrarla al terminar a los 125 s (bug encontrado probando por voz).
- Se anota **lo que Numa llegó a decir**: `hablar()` devuelve las frases
  entregadas a la voz; si la interrumpes, el resto ni existe.
- La memoria llega al LLM en **dos formatos**:
  - **Clasificar:** texto plano DENTRO del mensaje ("Conversación
    reciente: … / Petición actual: …"). Como turnos `assistant` en lenguaje
    natural, le enseñaría a responder con frases en vez de JSON.
  - **Conversar:** mensajes de chat (`Peticion.historial`).
- **`Skill.pista_contexto`**: pista para el LLM que se añade a la
  descripción SOLO si hay conversación reciente (temporizador: "si piden
  'otro igual', copia cantidad y unidad").
- **Honestidad en `conversar`:** "Tú no puedes hacer acciones: nunca digas
  que has puesto un temporizador…".

## Datos que llevaron a la decisión

Batería de 10 casos, 2 rondas, llama3.2:3b:

| Variante | Aciertos | Fallo |
|---|---|---|
| A. Contexto en el mensaje | 4/5 | "pon otro igual" → conversar… que dijo "Otro temporizador de 5 minutos en marcha" SIN crearlo |
| B. + ejemplo genérico en el cerebro | 5/5 | pero ata el cerebro a una skill |
| C. Contexto en el mensaje de sistema | 3/5 | |
| D. Ejemplo en la descripción del temporizador | 6/7 | sin contexto, se inventa un temporizador de 30 min |
| E. D + "si no hubo ninguno, no es esta intención" | 7/10 | rompe "media hora" (→ 30 horas) |
| **F. Pista solo si hay contexto** | **9/10** | "pon otro igual" tras hablar de Roma → temporizador inventado |

Honestidad en `conversar` con historial de temporizador: 2/3 mentiras → 0/3.

## Alternativas consideradas

- **Memoria en `ClienteLLM`:** mezcla hablar con Ollama y recordar, y no
  sabría lo resuelto por la regex.
- **5 turnos sin caducidad:** contaminación entre temas y más tokens.
- **Anotar la respuesta completa:** con streaming ni siquiera existe si
  se interrumpe; la memoria diría cosas que no sonaron.

## Consecuencias

- "pon otro igual", "otro de diez", "¿y su primer emperador?" funcionan.
- La regex no usa memoria (no la necesita); sus turnos sí se anotan.
- La memoria no crea capacidades: "¿y mañana?" tras el tiempo entiende
  la intención, pero la skill solo sabe el tiempo de ahora.
- Limitación medida: "pon otro igual" tras un tema sin temporizador puede
  inventarse uno (30 min). Numa lo anuncia, así que se puede corregir.
- Cada cambio en un prompt puede romper otros casos: medir siempre con la
  misma batería (variante E).
