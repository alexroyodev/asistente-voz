# ADR 0008: Streaming del LLM a la voz por frases

- **Estado:** aceptada
- **Fecha:** 2026-11-06

## Contexto

Con el LLM, Numa no empezaba a hablar hasta tener la respuesta entera
("Háblame de la historia de Roma": ~2 s en `PENSANDO`). Medido con
llama3.2:3b: el primer token llega en 20-45 ms; lo lento es terminar.

| Pregunta | Respuesta entera | Primera frase (streaming) |
|---|---|---|
| Historia de Roma (576 car.) | 2019 ms | 816 ms |
| ¿Por qué el cielo es azul? (1 frase larga) | 1167 ms | 923 ms |
| Gracias, Numa (corta) | 174 ms | 166 ms |

Otras palancas descartadas por ahora: bajar el silencio de fin de frase
(0,8 → 0,6 s; ya cortaba pausas) y Whisper `small` (falla con habla rápida).

## Decisión

- **Streaming de Ollama** (`ClienteLLM.charlar_en_flujo`, `stream=True`):
  generador perezoso; la petición sale al pedir la primera frase.
- **`trocear()`** (`asistente/trocear.py`) convierte tokens en frases: corta
  en `. ! ? …` seguido de espacio (mínimo 12 caracteres) y, si el trozo
  pasa de 80 caracteres sin fin de frase, en la última coma (`, ; :`).
- **Contratos:** `Respuesta.frases` (iterador opcional; solo lo usa
  `ConversarSkill`) y `Voz.decir_frases()`. `VozPiper` lo reimplementa con
  un solo lock y un solo `clear()` para que `parar()` corte TODO el flujo;
  `decir()` pasa a ser `decir_frases([texto])`.
- `hablar()` **cierra el flujo** al terminar o al ser interrumpido: el
  cierre llega en cadena hasta el generador de Ollama, que corta la
  conexión y deja de generar.
- Los fallos del LLM a mitad se capturan **dentro del flujo**
  (`_a_prueba_de_fallos`): una excepción de un generador sale donde se
  consume (en `decir_frases`, ya en `HABLANDO`), no donde se creó.
- Se registra "Primera frase lista en X ms": con streaming, "Pensado" solo
  mide elegir skill.

## Alternativas consideradas

- **`decir()` que acepte texto o iterador:** un método con dos
  comportamientos según el tipo; más difícil de leer y testear.
- **Cortar solo en fin de frase:** pausas siempre naturales, pero con frases
  largas apenas se gana (cielo azul: ~0,9 s igual).
- **Un hilo que sintetice la frase siguiente mientras suena la actual:**
  quitaría las pequeñas pausas entre frases; más complejidad. Pendiente.

## Consecuencias

- Medido en el asistente: Roma, primera frase a los 749 ms (antes ~2 s);
  cielo azul, 1189 ms (antes ~1,7 s). Las respuestas cortas, igual.
- El estado `HABLANDO` empieza antes de que exista la respuesta: los
  primeros cientos de ms de `HABLANDO` son el LLM escribiendo (y ya se
  puede interrumpir).
- Abreviaturas seguidas de espacio ("27 a.C. hasta") parten la frase:
  pausa rara, no error.
- Entre frase y frase hay una pausa corta: Piper sintetiza la siguiente
  después de terminar de decir la actual.
- La respuesta completa tarda lo mismo o algo más; lo que baja es la
  latencia PERCIBIDA.
