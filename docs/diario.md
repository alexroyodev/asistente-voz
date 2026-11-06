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

## 2026-11-04 — Bucle de eventos: adiós al eco

**Objetivo:** que los avisos del temporizador no hablen mientras el
asistente escucha (eco).

**Hecho:**
- Patrón productor-consumidor con `queue.Queue` (ADR 0004, propuesta).
  Decisiones mías: transición `REPOSO → HABLANDO` para avisos proactivos y
  que los avisos esperen en la cola. Código de Claude, explicado paso a paso.
- `eventos.py` (Activar, Frase, Aviso, Salir), `entrada.py` (hilo que
  convierte Enter/texto en eventos), bucle principal con `match`, y el
  temporizador publica `Aviso` en vez de hablar.
- Desaparecen `OidoTeclado` y el `input()` de `OidoWhisper`.
- Probado con micro: un Enter pulsado durante el aviso espera a que
  termine; un temporizador que vence mientras pido un chiste suena después.
- Tests: 58/58.

**Aprendido:**
- **Productor-consumidor:** los otros hilos no actúan, solo avisan; un único
  hilo (el principal) habla, escucha, imprime y cambia de estado. El eco
  queda imposible por construcción, y la máquina de estados ya no necesita Lock.
- Eventos como dataclasses `frozen=True`: inmutables → se pueden pasar entre
  hilos sin Lock. Una clase por evento: los errores de nombre saltan al momento.
- `match`/`case` despacha por tipo y extrae campos: `case Frase(texto=texto)`.
- `Queue` es segura entre hilos (lleva su Lock dentro) y `get()` duerme sin CPU.
  En Windows, `get()` sin timeout no deja pasar Ctrl+C → `get(timeout=0.2)`.
- **Hilos daemon:** Python no los espera al salir y los corta en seco, sin
  ejecutar ni su `finally`. Útil para hilos imposibles de parar (bloqueados
  leyendo el teclado); peligroso si tocan recursos compartidos.
- `input()` coge el lock de stdout: un hilo daemon dentro de `input()` al
  cerrar provocaba "Fatal Python error". `sys.stdin.readline()` solo lee.
  Era intermitente: con concurrencia, probar varias veces.
- Los valores por defecto se evalúan al definir la función: `leer=input`
  capturó el `input` original y el `monkeypatch` no tuvo efecto.
  → Inyectar dependencias explícitamente.
- Las excepciones en un hilo no llegan al principal: el hilo de entrada
  publica `Salir()` en su `finally` para no dejar el bucle esperando.
- Cambiar una regla debe romper algún test: `test_transicion_invalida`
  usaba justo `REPOSO → HABLANDO`. Se cambia el test a sabiendas.
- La inyección de `avisar` (fase 1) pagó por tercera vez: print →
  voz.decir → cola.put, sin tocar la skill.

**Problemas / dudas:**
- La voz `davefx` me da algo de miedo. Hay alternativas en español
  (sharvard, es_AR-daniela-high, es_MX-claude-high…): probar con calma.
- Siguen abiertos: el silencio de fin de frase (pausas), modo CPU para
  Whisper, guardar temporizadores al salir.

**Siguiente:** revisar ADR 0003 y 0004; fase 4 (palabra de activación),
que solo necesita un nuevo productor de `Activar()`.

### Añadido: ADR y voces

- ADR 0003 y 0004 aceptados.
- `experimentos/probar_voces.py`: misma frase con todas las voces en español
  (descarga las que falten, prueba cada hablante, ajusta velocidad y variación).
- Probadas varias; ninguna me convence más: **me quedo con `davefx`**.
- Aprendido: la calidad (x_low…high) es el tamaño del modelo; como Piper va
  en CPU, una voz mejor no quita VRAM. Una entonación demasiado regular da
  sensación de "valle inquietante".

---

## 2026-11-04 — Fase 4 (paso A): "Oye Numa"

**Objetivo:** activar el asistente con la voz, con una palabra en español.

**Hecho:**
- Decisiones mías: frase "Oye Numa"; detector provisional con VAD + Whisper
  (paso A) y openWakeWord más adelante (paso B); orden directa si va detrás
  de "Numa"; detector en pausa fuera de REPOSO; pitido; Enter y voz
  conviven. Código de Claude, explicado paso a paso. ADR 0005 (propuesta).
- `experimentos/probar_numa.py`: con mi voz, "Oye Numa" 7/7, órdenes en un
  tirón separadas bien, 0 falsos positivos en una frase normal.
- `asistente/activacion.py`: hilo productor que segmenta el audio continuo,
  transcribe con el MISMO Whisper y publica `Activar()` o `Frase(orden)`.
- `Voz.pitar()`; `OidoWhisper.transcribir()` público; `--sin-numa`.
- Probado: "Oye Numa" → bip → orden → respuesta; "Oye Numa, cuéntame un
  chiste" → respuesta directa. Tests: 75/75.

**Aprendido:**
- Wake word: modelo diminuto que escucha siempre y solo dice "¿me han
  llamado?". Dos errores opuestos: falsos rechazos y falsos positivos.
- openWakeWord solo entrena en inglés (datos sintéticos de un TTS inglés)
  y solo en Linux. Truco: pronunciación aproximada ("noo-mah").
- Palabras cortas = más falsos positivos; "Numa" se parece a "una",
  "luna", "nunca"… → "Oye Numa".
- `hotwords` sesga a Whisper hacia palabras que no conoce: sin pista,
  "Oye Numa" salía "¿O tiene número?". Con orden detrás acierta sin pista:
  el contexto ayuda.
- Con Whisper, "Oye Numa, <orden>" sale gratis en un turno; openWakeWord
  solo detecta, no transcribe.
- Compartir el modelo entre hilos: no cargar Whisper dos veces (VRAM).
- Check-then-act: comprobar la bandera al grabar Y antes de publicar,
  porque transcribir tarda ~600 ms y el mundo cambia entre medias.
- Cada productor decide su política de fallo según lo esencial que sea:
  sin teclado → Salir(); sin detector → seguir con Enter.
- Dobles de test: un VAD falso por volumen basta para probar `segmentar`;
  solo tiene que respetar el contrato, no la implementación.
- `` en la regex: "numérico" no activa.
- Pitido sin chasquidos: rampas de 10 ms al principio y al final.
- Escapes anidados: escribir código desde otro programa puede convertir
  un `
` en un salto de línea real.

**Problemas / dudas:**
- Falsos positivos con tele/conversación: sin medir todavía.
- Whisper transcribe todo lo que se habla en REPOSO: GPU continua.
- Dos grabaciones simultáneas del micro: bien en Windows (MME); ¿y en Linux?

**Siguiente:** aceptar el ADR 0005; decidir entre paso B (openWakeWord) o
fase 5 (LLM local con Ollama).

---

## 2026-11-04 — Fase 5: Numa tiene cerebro (LLM local)

**Objetivo:** entender frases que no encajan en las regex y poder conversar.

**Hecho:**
- Ollama + llama3.2:3b. Experimentos comparando modelos y enfoques
  (`experimentos/probar_ollama.py`), ADR 0006 (propuesta).
- Decisiones mías: regex primero y LLM si no encaja; el LLM conversa con
  prudencia; cada skill declara sus parámetros; sin Ollama, se sigue sin LLM.
  Código de Claude, explicado paso a paso.
- `Skill.parametros`; `cerebro.py` (esquema, instrucciones, validación,
  `ClienteLLM`, `Cerebro`); `ConversarSkill`; `--sin-llm`, `--llm`.
- Probado por voz: paraguas → tiempo, capital de Francia → París, gracias →
  "Buenos días…". "Temporizador de 5 minutos" fue por regex (Whisper
  escribe cifras). Tests: 93/93.

**Aprendido:**
- LLM: predice el siguiente token. Ollama lo sirve en local; Q4 = pesos de
  4 bits. `num_ctx` (tamaño de la caché) decide si cabe en la GPU: con 2048,
  llama3.2:3b cabe al 100 %; con 4096, al 80 % (y lo que va a CPU es lento).
- Tool calling con modelos pequeños: abusan de las tools ("hora" para la
  capital de Portugal) o, con una tool "conversar", dejan de usarlas y se
  inventan datos ("parece que lloverá"). 5/7 y 8/10.
- **Salida estructurada** (JSON Schema con un `enum` de intenciones): 10/10,
  330-450 ms. Al modelo pequeño se le da mejor clasificar que decidir si actuar.
- Un 3B sabe poco y se equivoca con seguridad: "una araña tiene seis patas",
  incluso con instrucciones de prudencia.
- Validar SIEMPRE lo que genera un LLM: `cantidad: null` cumple el esquema
  y no tiene sentido; `isinstance(True, int)` es True.
- `conversar` como skill sin patrones: polimorfismo del contrato Skill.
- Las descripciones de las skills son comportamiento, no documentación.
- Comprobar hipótesis antes de "arreglar": "Me quiero fumar un porro" →
  chiste. Pensé que era la descripción; la cambié, medí, y no: es el modelo.
  Se deja como está.
- Un `enum` cerrado obliga a elegir siempre algo: `conversar` es la red de
  seguridad para lo raro.
- Ollama es OTRO proceso: con keep_alive=-1 retenía 2,3 GB de VRAM tras
  cerrar el asistente. Hay que descargarlo al salir (desde el hilo principal).
- `cmd | tail` oculta errores (el código de salida es el de tail):
  `set -o pipefail`. Otra vez escapes rotos al escribir código desde código.

**Latencias medidas:**
- llama3.2:3b (ctx 2048, 100 % GPU): clasificar 400-550 ms; conversar,
  otra llamada (~400-800 ms). Carga ~5 s al arrancar.
- VRAM con todo (Whisper turbo + LLM + detector): ~3,2 GB de 4.
- Percibida por la vía LLM: ~0,8 s silencio + ~0,6 s Whisper + ~0,5 s LLM
  (+ red o 2ª llamada) + Piper ≈ 2-2,5 s.

**Problemas / dudas:**
- Alucinaciones del 3B en cultura general (riesgo asumido).
- "Me quiero fumar un porro" → chiste (rareza del modelo).
- No probé aún "Oye Numa, <orden>" de un tirón con frases que van al LLM.

**Siguiente:** aceptar el ADR 0006; fase 6 (interrupciones, latencia,
memoria corta) o paso B de la fase 4 (openWakeWord).

---

## 2026-11-06 — Fase 6: interrumpir a Numa

**Objetivo:** cortar a Numa mientras habla diciendo "Oye Numa".

**Hecho:**
- `experimentos/probar_interrupcion.py`: Piper habla y el micro escucha a la
  vez; ventanas solapadas; puerta de volumen.
- Decisiones mías: el detector llama a `voz.parar()`; tras cortar, por
  REPOSO; "para/cállate" solo calla; analizar cada 0,75 s. Código de Claude
  explicado paso a paso. ADR 0007 (propuesta).
- `asistente/interrupcion.py` (segundo detector, solo en HABLANDO) y
  `hablar()` en el bucle. Probado: corta la historia de Roma, una respuesta
  del LLM y el aviso "¡Tiempo!"; nunca se corta solo. Tests: 120/120.

**Aprendido:**
- *Barge-in*: hablar y escuchar a la vez. Los altavoces comerciales usan
  cancelación de eco (AEC); aquí no ha hecho falta.
- Mientras Piper habla no hay silencio: el VAD no sirve para cortar frases
  → ventanas fijas (2 s cada 0,75 s, solapadas).
- Primer experimento: "Oye Numa" detectado a los 1,5 s… sin que yo hablara.
  Hipótesis 1 ("Hoy hace" ≈ "Oye Numa"): FALSA (con audio limpio, 0
  falsos). Hipótesis 2: el micro apenas oye a Piper (pico ~0,003) y, con
  audio débil, la pista `hotwords` hace que Whisper alucine la propia pista.
  Cierta (2/16 ventanas; 4/16 con vad_filter).
- **Puerta de volumen**: mi voz llega ~40 veces más fuerte (0,12) que Piper.
  Umbral 0,005: 0 falsos positivos y Whisper ni se ejecuta con Piper.
  Medir el PICO de 100 ms, no la media de 2 s (la media diluye la voz).
- Bug del contador de ventanas: poner a 0 en vez de restar el paso hace que
  "cada 0,75 s" sea "cada 0,8 s" (deriva acumulada).
- Periodo refractario: tras cortar, ignorar una ventana; si no, las
  ventanas solapadas oyen el final de mi frase y cortan la respuesta.
- Con ventanas la orden puede llegar cortada ("Oye Numa, qué"): al
  interrumpir, solo callar o Activar() (bip y repetir la orden).
- `parar()` (escrito en la fase 2 para llamarse desde otro hilo) se usó por
  fin. `hablar()` con `finally` para que la bandera no se quede activada.
- UX: con una pausa entre "Oye Numa" y "para", el "para" llegaba tras el
  bip como orden normal y el LLM se ponía a charlar. Las órdenes de callar
  (1-2 palabras) se filtran ahora en TODOS los caminos.

**Latencias medidas:**
- Corte de Piper: ~0,8-1,6 s desde que digo "Oye Numa" (paso 0,75 s +
  ~0,6 s de Whisper).
- "Háblame de la historia de Roma": Pensado en ~2 s (clasificar ~0,5 s +
  redactar ~1,5 s). Con respuestas largas, el LLM es ahora lo más lento.

**Problemas / dudas:**
- El umbral depende del hardware: recalibrar con otros altavoces o en la Pi.
- Palabras sueltas mal transcritas: "Para" → "Fuma" → chiste.
- La flecha ⑨ (HABLANDO → ESCUCHANDO) sigue sin usarse.

**Siguiente:** aceptar ADR 0005 y 0007; fase 6 sigue: latencia (empezar a
hablar mientras el LLM genera) o memoria corta.

---

## 2026-11-06 — Fase 6: latencia (streaming del LLM a la voz)

**Objetivo:** que Numa empiece a hablar antes con las respuestas del LLM.

**Hecho:**
- Medido: el primer token llega en 20-45 ms; lo lento es terminar.
- Decisiones mías: solo streaming (sin tocar el silencio de fin ni
  Whisper); `Respuesta.frases` + `Voz.decir_frases`; cortar en fin de frase
  y en comas si el trozo es largo. Código de Claude explicado paso a paso.
  ADR 0008 (propuesta).
- `trocear.py`, `ClienteLLM.charlar_en_flujo`, `ConversarSkill` con flujo,
  `hablar()` que cierra el flujo, log "Primera frase lista".
- Probado por voz: Roma, primera frase a los ~0,8-1 s (antes ~2 s);
  interrumpida tras el primer trozo, y "Para." tras el bip calla. Tests: 136/136.

**Aprendido:**
- Latencia PERCIBIDA frente a total: con streaming la respuesta completa
  tarda lo mismo, pero empieza a sonar ~1,2 s antes en respuestas largas.
- Pipeline perezosa de generadores (LLM → trocear → decir_frases): nadie
  pide el siguiente dato hasta necesitarlo. Ollama sigue generando en su
  proceso mientras Piper habla: paralelismo sin crear hilos.
- Un "." al final de lo recibido aún no es fin de frase: puede venir ",",
  un número… Solo con el espacio detrás se sabe. Abreviaturas ("a.C. hasta")
  parten la frase: pausa rara aceptada.
- `parar()` debe cortar TODO el flujo: un solo `clear()` para el flujo
  entero; `decir()` pasa a ser `decir_frases([texto])`.
- Las excepciones de un generador salen donde se CONSUME, no donde se crea:
  el try/except de `pensar()` ya no las ve → capturar dentro del flujo.
- Cerrar el flujo (`close()`) propaga `GeneratorExit` en cadena hasta el
  generador de Ollama: si no, seguiría generando para nadie tras interrumpir.
- Con streaming, "Pensado en" ya no mide lo que se nota: nueva métrica
  "Primera frase lista". Cambiar el diseño obliga a revisar las métricas.
- Un test que no puede fallar no sirve (rehíce uno con un `or` que siempre
  se cumplía).

**Latencias medidas:**
- Roma: primera frase 749-978 ms (antes ~2000). Cielo azul: 1189 ms (antes
  ~1700). Cortas, igual. Clasificar sigue costando ~0,5-0,7 s.

**Problemas / dudas:**
- Pausa corta entre trozos (Piper sintetiza el siguiente al acabar el actual).
- Idea: ahorrar la llamada de clasificar cuando es obviamente charla, o
  clasificar y responder en una sola llamada.

**Siguiente:** aceptar ADR 0008; memoria corta (último frente de la fase 6).

---

## AAAA-MM-DD — Título

**Objetivo:**
**Hecho:**
**Aprendido:**
**Problemas / dudas:**
**Latencias medidas:**
**Siguiente:**
