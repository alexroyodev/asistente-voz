# ADR 0004: Bucle de eventos con un único hilo dueño del audio y del estado

- **Estado:** propuesta
- **Fecha:** 2026-11-04

## Contexto

En la fase 3 apareció el eco: el aviso del temporizador hablaba desde su
propio hilo mientras el bucle principal ya estaba en `ESCUCHANDO`, así que
el micrófono podía grabar al propio asistente. El `Lock` de `Voz` (ADR 0002)
impedía que dos voces se solaparan, pero no que se escuchara mientras se
hablaba, y la máquina de estados no se enteraba de los avisos.

Además, el hilo principal se bloqueaba esperando el Enter dentro de
`OidoWhisper.escuchar()`, así que no podía atender nada más mientras tanto.

## Decisión

Patrón **productor-consumidor** con una `queue.Queue`:

- **Eventos** (`asistente/eventos.py`): `Activar`, `Frase(texto)`,
  `Aviso(texto)`, `Salir`. Dataclasses inmutables (`frozen=True`).
- **Productores** (otros hilos) solo publican eventos, nunca actúan:
  - hilo de entrada (`asistente/entrada.py`): Enter → `Activar()`, texto
    (`--teclado`) → `Frase`, fin de entrada → `Salir()`. Es daemon y lee
    con `sys.stdin.readline()`.
  - temporizador: `avisar` publica `Aviso(texto)` (vía `cargar_skills(avisar=...)`).
- **Consumidor único**: el hilo principal. Es el único que habla, escucha,
  imprime el prompt y cambia de estado. Atiende un evento cada vez, de
  principio a fin (`match` sobre el tipo de evento).
- Un aviso que llega mientras se atiende otra cosa **espera en la cola**.
- Nueva transición `REPOSO → HABLANDO` (aviso proactivo).
- `OidoWhisper.escuchar()` ya no espera el Enter: graba en cuanto se le llama.
  `OidoTeclado` desaparece (con `--teclado` el texto llega en `Frase`).

## Alternativas consideradas

- **Más locks** (p. ej. que `Voz` y `Oido` compartan uno): parchea el
  síntoma; el estado seguiría repartido entre hilos y la máquina de estados
  seguiría sin enterarse de los avisos.
- **Atender los avisos solo al final de cada turno**: si el bucle está
  bloqueado esperando el Enter, el aviso no sonaría hasta que pulsaras.
- **El aviso interrumpe la grabación**: más puntual, pero se pierde lo que
  estabas diciendo y requiere cancelar la grabación desde fuera (fase 6).
- **Pasar por `PENSANDO` en los avisos** en vez de añadir `REPOSO → HABLANDO`:
  `PENSANDO` sería falso y los logs confundirían.

## Consecuencias

- El eco es imposible por construcción: solo un hilo usa altavoz y micrófono.
- `MaquinaEstados` no necesita `Lock`: solo la toca el hilo principal.
- En la fase 4, la palabra de activación será otro productor de `Activar()`;
  el bucle principal no cambia.
- Un aviso puede llegar con retraso (lo que dure el turno en curso).
- Un Enter pulsado mientras el asistente habla queda encolado: al terminar,
  empieza a escuchar enseguida.
- `cola.get()` usa `timeout=0.2` para que Ctrl+C funcione en Windows.
- Los hilos daemon se cortan en seco al salir (sin `finally`): los
  temporizadores pendientes se pierden; guardarlos tendría que hacerlo el
  hilo principal.
- Si un productor muere por una excepción, publica `Salir()` en su
  `finally`: el bucle nunca se queda esperando eventos que no llegarán.
