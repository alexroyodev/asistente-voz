# Diario de desarrollo

Una entrada por sesión. Corto y honesto: lo que falló es lo más valioso.

---

## 2026-10-30 — Arranque

**Objetivo:** decidir enfoque y montar el esqueleto de la fase 1.

**Hecho:**
- Investigado el panorama: Home Assistant Assist, OpenVoiceOS (heredero de
  Mycroft), protocolo Wyoming, openWakeWord, Whisper, Piper, Ollama.
- Decidido construir el núcleo yo mismo (ver ADR 0001).
- Esqueleto en modo texto: máquina de estados, router por regex, skill de hora.
- Repaso de la arquitectura: el centro (estados, router, skills) es estable;
  lo que cambia de fase en fase son los extremos (entrada y salida).
- `estado.py`: `transicionar()` ya valida contra `TRANSICIONES` y lanza
  `TransicionInvalida`. (Lo escribió Claude a petición mía, explicado línea a línea.)

**Aprendido:**
- Validar antes de mutar: si la comprobación falla, el estado sigue siendo válido.
- La lógica está en los datos (la tabla), no en `if`s: para permitir una
  transición nueva solo se toca la tabla.
- ¿Por qué fallar ruidosamente? Una transición ilegal ignorada en silencio
  deja el sistema en un estado que no corresponde a la realidad (p. ej. "creo
  que escucho" mientras hablo), y el fallo aparece mucho después y lejos de
  su causa. La excepción lo señala en el momento y el lugar exactos.
- `TRANSICIONES[estado]` con corchetes (no `.get`) también falla ruidosamente
  si olvido añadir un estado nuevo a la tabla.
- El orden de las reglas del router importa: gana la primera que encaja.

**Problemas / dudas:**
- Fase 4: varios hilos llamando a `transicionar()` a la vez → condición de
  carrera entre comprobar y asignar. Solución prevista: `threading.Lock`.

**Siguiente:** temporizador (hilos) y tiempo (red + errores).

---

## 2026-11-03 — Temporizador

**Objetivo:** temporizador que avise sin bloquear al asistente.

**Hecho:**
- `skills/temporizador.py`: `ejecutar()` con `threading.Timer` (hilo daemon).
- Tests: 10 en verde; faltan los 2 del tiempo.

**Aprendido:**
- Un `Timer` es un hilo aparte que espera y luego llama a una función: la
  skill responde al instante y el aviso llega después.
- Se pasa `self._avisar` sin paréntesis (la función, no su resultado), y sin
  `.start()` el `Timer` no hace nada.
- `daemon = True`: el hilo no mantiene vivo el programa. Al salir, los
  temporizadores pendientes se pierden en silencio.
- Las entidades de la regex llegan como texto: hay que convertir con `int()`.
- Dos temporizadores a la vez funcionan (un hilo cada uno), pero no se
  pueden cancelar: no guardo referencia a ellos.

**Problemas / dudas:**
- El aviso se imprime desde otro hilo, en mitad del prompt `> `, y se salta
  la máquina de estados. En la fase 2 serían dos voces a la vez.
  Idea: que el `Timer` encole un evento y el bucle principal lo procese en
  `REPOSO` (germen del bucle de eventos de la fase 4).
- Pendiente: persistir temporizadores en disco y una skill "cancela el
  temporizador" (lista `self._timers` + `.cancel()`).

**Siguiente:** `tiempo.py` (red + manejo de errores). Escribirlo yo.

---

## 2026-11-03 — Tiempo (fin de la fase 1)

**Objetivo:** skill del tiempo con Open-Meteo que no reviente si falla la red.

**Hecho:**
- `skills/tiempo.py`: `ejecutar()` escrito por mí; corregido tras revisión.
- Tests: 12/12 en verde → **fase 1 terminada**.

**Aprendido:**
- `except Exception` es demasiado amplio: un bug mío (una errata, un
  `NameError`) acabaría como "lo siento" y nunca lo vería. Mejor capturar
  solo lo que espero: `OSError` (red/timeout; `URLError` y `TimeoutError`
  heredan de él) y `KeyError`/`ValueError`/`TypeError` (respuesta rara).
- Si capturo un error, lo registro con `log.warning`: disculparse ante el
  usuario no significa esconderlo de mí.
- El `try` solo debe envolver lo que puede fallar por causas externas.
- `18.4` pasaba el test (`"18" in "18.4"`), pero en voz sería "dieciocho
  coma cuatro": `round()`. Un test que pasa no garantiza que esté bien.
- "Está lluvia débil" no suena bien: la frase debe funcionar con todas las
  descripciones de la tabla. Si el código no está en la tabla, mejor omitir
  la descripción que decir "desconocido".

**Latencias medidas:**
- Consulta real a Open-Meteo: ~230 ms (una medida). Aceptable, pero en
  voz se sumará a STT + TTS.

**Problemas / dudas:**
- Si no hay red, el usuario espera hasta 5 s (el `timeout`) antes de oír
  la disculpa. ¿Bajarlo? ¿Cachear el último dato unos minutos?

**Siguiente:** fase 2, salida de voz con Piper.

---

## 2026-11-03 — Reto: skill de chistes

**Objetivo:** primera skill diseñada desde cero, sin repetir chiste seguido.

**Hecho:**
- `skills/chiste.py`: `ejecutar()` escrito por mí; corregido tras revisión.
  Registrada en `cargar_skills()`.
- Tests: 17/17 en verde (añadido uno de regresión por el bug de abajo).

**Aprendido:**
- Mi versión repetía el sorteo `while chiste == self._ultimo and len > 1`.
  Bug: con elementos duplicados (`("a", "a")`) `len > 1` es cierto pero
  nunca sale otro distinto → **bucle infinito**. El asistente se colgaría
  sin error ni log. Contaba elementos, no valores distintos.
- Mejor construir la lista de candidatos (todos menos el último) y, si queda
  vacía, permitir repetir: siempre termina, en una sola elección.
- Un bucle `while` que depende del azar para terminar es sospechoso por
  defecto: hay que demostrar que siempre sale.
- Inyectar `random.Random` hace el azar reproducible en los tests.
- Primera skill con estado (`self._ultimo`): funciona porque hay una única
  instancia de cada skill durante todo el programa.

**Problemas / dudas:**
- Con estado en la skill, si en la fase 7 hay varios satélites, todos
  compartirían el mismo "último chiste". El estado de conversación debería
  ir por usuario/sesión, no en la skill.
- "No repetir el último" permite A, B, A, B… Mejora: barajar (`shuffle`)
  y recorrer la lista entera antes de repetir.

**Siguiente:** fase 2, salida de voz con Piper.

---

## 2026-11-03 — Fase 2: el asistente habla (Piper)

**Objetivo:** sustituir el `print` por voz, detrás de una interfaz propia.

**Hecho:**
- Instalado `piper-tts`, `sounddevice`, `numpy`; voz `es_ES-davefx-medium`
  en `modelos/` (ignorada en git).
- `experimentos/probar_piper.py`: Piper suelto, fuera del asistente, midiendo.
- `asistente/voz.py`: contrato `Voz` + `VozTexto` + `VozPiper`. Decisiones
  mías (bloquea, `parar()` opcional, `Lock` en cada voz); código de Claude.
- `__main__.py`: Piper por defecto, `--texto` para no usar audio.
  `cargar_skills(voz)` pasa `voz.decir` al temporizador.
- ADR 0002 (contrato `Voz` + Piper en CPU), redactado por Claude: revisarlo.
- Tests: 21/21 (4 nuevos de voz, incluido uno de concurrencia).

**Aprendido:**
- Piper: TTS neuronal local, modelo ONNX (~63 MB), va bien en CPU → la VRAM
  queda para Whisper y el LLM. `synthesize()` es un generador: un trozo por
  frase, así puede empezar a sonar antes de sintetizarlo todo.
- **Lock** = exclusión mutua ("baño con una llave"): un solo hilo dentro a
  la vez; los demás esperan. Es un semáforo de una plaza.
  **Semaphore(n)** = como mucho n a la vez ("parking con n plazas").
- `with lock:` en vez de `acquire()/release()`: devuelve la llave aunque
  haya una excepción. Si no, el asistente se quedaría mudo para siempre.
- **Event** = bandera (`set/clear/is_set`): para avisar entre hilos, no para
  impedir el paso.
- `parar()` NO puede usar el lock de `decir()`: esperaría a que acabe justo lo
  que quiere cortar (deadlock). Regla: cancelar nunca necesita el mismo lock
  que la operación que cancela.
- Cargar el modelo cuesta ~3 s: una vez al arrancar, nunca en `decir()`.
- Si `decir()` bloquea, medir "al final" incluye la duración del audio: la
  métrica cambió de significado sin tocarla. Ahora mido "pensado" y "turno".
- Medir varias veces: la primera síntesis tras instalar tardó 1653 ms
  (arranque en frío); después, 40-85 ms.

**Latencias medidas (CPU):**
- Carga del modelo: ~3-5 s. Primer trozo de audio: ~80 ms. RTF ≈ 0,39.
- "Qué tiempo hace": pensado en ~240 ms (casi todo es la red); turno ~3 s.

**Problemas / dudas:**
- Los avisos del temporizador siguen saltándose la máquina de estados.
  El `Lock` evita que se pisen, pero el orden entre dos avisos simultáneos
  no está garantizado. Cola de eventos → fase 4.
- `parar()` escrito pero sin probar: fase 6.
- `MaquinaEstados.transicionar()` necesitará su propio `Lock` (comprobar +
  asignar de forma atómica) cuando haya varios hilos.
- Piper lee "17:48" como "diecisiete cuarenta y ocho": en voz, el texto de
  la respuesta es interfaz. Ejercicio: que `HoraSkill` diga "las seis menos doce".
- Ctrl+C mientras habla no está controlado (solo se captura en `input()`).

**Siguiente:** revisar y aceptar el ADR 0002; ejercicio de `HoraSkill`;
después, fase 3 (faster-whisper + VAD, pulsar para hablar).

---

## 2026-11-03 — Hora natural, git y cierre de la fase 2

**Objetivo:** que la hora suene humana con Piper y poner el proyecto en git.

**Hecho:**
- Repositorio git (`main`) enlazado a GitHub (`origin`). Commits a mi nombre.
- README actualizado: arquitectura actual, uso (`--texto`, `-v`), fases.
- ADR 0002 revisado y **aceptado**.
- `HoraSkill`: nueva función pura `decir_hora(hora, minuto)`. La lógica de
  horas la escribí yo (12 de 16 tests); la reestructuración final, Claude.
- Tests: 35/35 (14 casos parametrizados de la hora).

**Aprendido:**
- `hora % 12` da 0 a las 0:00 y a las 12:00 → corregir a 12. Y para la hora
  siguiente, `(hora_12 % 12) + 1`: así de 12 se pasa a 1, nunca a 13.
  Respuesta del diario: 23:50 → "las 12 menos 10"; 12:50 → "la 1 menos 10".
- Mi primera versión tenía `"Son las"` copiado en 6 ramas y por eso se me
  escapó el singular ("Es la 1"). Si un mismo dato está repetido en N
  sitios, cada regla nueva hay que aplicarla N veces. Mejor: calcular las
  partes (`hora_final`, `resto`) y montar la frase en un único `return`.
- Un dict con `.get(clave, por_defecto)` sustituye a una cadena de `elif`
  para los casos con nombre propio ("en punto", "y cuarto", "y media").
  Ojo: el valor por defecto se evalúa siempre.
- Separar "obtener datos" (reloj, en `ejecutar`) de "transformarlos"
  (`decir_hora`, función pura) permite testear con una tabla de casos.
- Los tests parametrizados diagnostican solos: los 4 fallos eran justo las
  horas que acaban en 1.
- En voz, el texto de la respuesta es parte de la interfaz.

**Problemas / dudas:**
- La hora es ambigua sin "de la mañana/tarde/noche". ¿Hace falta?
- Siguen abiertos (ver entrada anterior): cola de eventos para avisos,
  `Lock` en `MaquinaEstados`, Ctrl+C mientras habla, `parar()` sin probar.

**Siguiente:** fase 3, entrada de voz con faster-whisper + VAD (pulsar
para hablar). Antes: ¿qué tamaño de Whisper cabe bien en 4 GB de VRAM?

### Añadido: franja del día

- Decisiones mías: franjas madrugada 1-5 · mañana 6-12 · tarde 13-20 ·
  noche 21-0; la franja la decide la hora QUE SE DICE (12:45 → "de la
  tarde"); especiales 12:00 "del mediodía" y 0:00 "de la noche".
  Código de Claude. Tests: 43/43.
- Aprendido: transformar pierde información. En 12 h el 6 puede ser 6:00 o
  18:00, así que la hora en 24 h hay que calcularla desde los datos
  originales (`(hora + 1) % 24`), no desde `hora_final`.
- Los casos especiales SUSTITUYEN partes de la frase (`complemento`), así se
  mantiene un único `return`.
- La noche es la única franja no contigua (21-23 y 0): por eso va en el `else`.
- Un test a cada lado de cada frontera (5:30/5:50, 20:30/20:59) pilla los
  errores de `<` frente a `<=`.

---

## 2026-11-03 — Fase 3: el asistente escucha (Whisper + VAD)

**Objetivo:** hablarle al asistente con "pulsar para hablar".

**Hecho:**
- faster-whisper en GPU con las DLL de CUDA instaladas por `pip` (sin
  CUDA Toolkit), registradas con `os.add_dll_directory`.
- `experimentos/probar_whisper.py`: comparativa small/turbo con mi micro.
- `asistente/oido.py`: contrato `Oido` + `OidoTeclado` + `OidoWhisper`.
  Decisiones mías (devuelve `None`, Enter empieza y el VAD termina, tres
  capas anti-alucinación, `--teclado`/`--texto` separados, modelo
  configurable con turbo por defecto); código de Claude.
- ADR 0003 (propuesta). Tests: 54/54.
- Primera conversación completa por voz: hora, temporizador, chiste, salir.

**Aprendido:**
- Whisper: voz → texto con un transformer; faster-whisper lo acelera con
  CTranslate2 y cuantización (int8). Tamaños: más grande = mejor y más lento.
- VAD (Silero): "¿hay voz en estos 32 ms?". Sirve para recortar silencios
  (evita alucinaciones) y para detectar el fin de frase.
- faster-whisper ya trae Silero en ONNX (`get_vad_model()`): sin PyTorch.
  No guarda estado entre llamadas → reevalúo todo lo grabado cada 100 ms
  (~4 ms por 2,4 s de audio).
- `transcribe()` devuelve un GENERADOR: la transcripción ocurre al consumir
  los segmentos. Medir solo la llamada da ~0 ms.
- Whisper escribe los números en cifras ("10"): por eso encaja con la regex
  del temporizador. No está garantizado: es una frontera ML → código a vigilar.
- Audio dudoso = más lento y peor (temperature fallback).
- `normalizar()` de la fase 1 ya compensa: quita "¿", tildes y puntos de
  Whisper (también para "Salir.").
- Las reglas por palabra clave toleran errores de transcripción: "¿Contamos
  un chiste?" sigue llegando a la skill de chistes.
- Lo difícil (¿ha acabado de hablar?, ¿me fío del texto?) en funciones puras:
  8 tests sin micrófono ni GPU.
- Primera vez que se recorre la máquina de estados entera:
  REPOSO → ESCUCHANDO → PENSANDO → HABLANDO → REPOSO.

**Latencias medidas (RTX 3050 Ti, int8_float16):**
- small: ~335 MiB VRAM, 340-470 ms, falla con habla rápida.
- turbo: ~880 MiB VRAM, 540-730 ms (1ª transcripción ~930 ms), entiende mejor.
- Percibida ≈ 0,8 s (silencio de fin) + ~0,6 s (Whisper) + ~0,08 s (Piper)
  ≈ 1,5 s. El mayor sumando es ESPERAR a confirmar que me he callado.

**Problemas / dudas:**
- Una pausa al hablar me cortó la frase ("que"): 0,8 s de silencio es poco
  para pausas, mucho para la latencia. Equilibrio del turn-taking.
- **Eco:** el aviso del temporizador habla desde otro hilo mientras el bucle
  ya está en ESCUCHANDO → el micro podría grabar a Piper. El problema de
  "los avisos se saltan la máquina de estados" ya tiene consecuencias.
- Hugging Face consulta internet al arrancar (comprobación de versión).
- Sin GPU, `OidoWhisper` no arranca (no hay modo CPU todavía).
- Pendiente probar `small` + `initial_prompt` para ahorrar VRAM.

**Siguiente:** aceptar el ADR 0003; decidir el silencio de fin; resolver el
eco (los avisos deben pasar por el bucle principal) antes de la fase 4.

---

## AAAA-MM-DD — Título

**Objetivo:**
**Hecho:**
**Aprendido:**
**Problemas / dudas:**
**Latencias medidas:**
**Siguiente:**
