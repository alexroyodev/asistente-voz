# ADR 0002: Salida de voz detrás de un contrato `Voz`, con Piper en CPU

- **Estado:** aceptada
- **Fecha:** 2026-11-03

## Contexto

En la fase 2 el asistente pasa de imprimir a hablar. Hay dos fuentes que
pueden querer hablar a la vez: el bucle principal (respuestas) y los hilos
de los temporizadores (avisos). Además, en la fase 6 habrá que poder
interrumpir al asistente a mitad de frase, y la GPU (4 GB de VRAM) tendrá
que alojar Whisper (fase 3) y un LLM (fase 5).

## Decisión

El núcleo solo conoce una clase abstracta `Voz` (`asistente/voz.py`) con:

- `decir(texto)`: **bloquea** hasta que termina el audio.
- `parar()`: opcional (por defecto no hace nada); **nunca** toma el lock.
- Seguridad entre hilos dentro de cada implementación: un `threading.Lock`
  serializa las llamadas a `decir()`.

Implementaciones: `VozTexto` (imprime) y `VozPiper` (Piper en **CPU** +
`sounddevice`, reproduciendo frase a frase). Se elige al arrancar: Piper por
defecto, `--texto` para no usar audio. Las skills que hablan por su cuenta
reciben la voz vía `cargar_skills(voz)`.

## Alternativas consideradas

- **`decir()` no bloqueante:** más flexible, pero obliga a notificar el fin
  del audio para volver a `REPOSO`. Innecesario hasta la fase 6.
- **`parar()` abstracto u omitido:** abstracto obligaba a implementarlo en
  `VozTexto` sin sentido; omitirlo obligaría a tocar todas las
  implementaciones en la fase 6.
- **Serializar en quien llama (cola de eventos):** más limpio a largo plazo,
  pero hoy el temporizador llama directamente y se pisaría con la respuesta.
- **Piper en GPU (`use_cuda`):** innecesario. En CPU el primer audio sale en
  ~80 ms con RTF ≈ 0,4, y la VRAM queda libre para Whisper y el LLM.
- **`winsound`:** sin dependencias, pero solo existe en Windows (fase 7 es
  una Raspberry Pi) y no permite cortar el audio limpiamente.

## Consecuencias

- Cambiar de TTS solo requiere una nueva subclase de `Voz`.
- Mientras habla, el asistente no puede hacer nada más en el hilo principal.
- Un aviso del temporizador que coincide con una respuesta espera a que
  termine: llega con retraso, pero entero.
- El orden entre dos avisos simultáneos no está garantizado (lo decide quién
  coge antes el lock).
- Los avisos siguen saltándose la máquina de estados (hablan desde otro hilo
  sin pasar a `HABLANDO`). Queda abierto: cola de eventos en la fase 4.
- `parar()` está escrito pero sin probar: se validará en la fase 6.
- Cargar Piper cuesta ~3 s al arrancar; `--texto` lo evita.
