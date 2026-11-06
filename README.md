# Asistente de voz propio

Asistente estilo Alexa construido desde el núcleo, como proyecto de
aprendizaje. Local, privado y en español.

## Arquitectura

Objetivo final:

```
micrófono → wake word → VAD → voz a texto → router / LLM → skills → texto a voz → altavoz
                         └──────────── máquina de estados ────────────┘
```

Hoy (fase 4): dices «Oye Numa» (o pulsas Enter), hablas, y el asistente responde.

```
micrófono → VAD (fin de frase) → Whisper → router ─┬─▶ skill → Voz (Piper) → altavoz
   └─────────────── Oido ──────────────┘    (regex) │      ▲         └──── Voz ────┘
                                     no encaja ──▶ LLM ────┘  (Ollama, llama3.2:3b)
                         └──────────── máquina de estados ────────────┘
```

El centro (estados, router, skills) no cambia entre fases; lo que cambia son
los extremos, cada uno detrás de una interfaz propia (`Oido`, `Skill`, `Voz`).

Concurrencia (ADR 0004): bucle de eventos productor-consumidor.

```
hilo de entrada (Enter / texto) ──▶ Activar / Frase ─┐
temporizadores                  ──▶ Aviso ───────────┼──▶ [cola] ──▶ hilo principal
detector «Oye Numa» (en REPOSO) ──▶ Activar / Frase ─┤    (único que habla, escucha
detector de interrupciones      ──▶ Activar ─────────┘     y cambia de estado)
  (en HABLANDO: voz.parar())
```

## Puesta en marcha (Windows, PowerShell)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m piper.download_voices es_ES-davefx-medium --data-dir modelos
python -m pytest
```

El LLM necesita Ollama (`winget install Ollama.Ollama`) y el modelo:
`ollama pull llama3.2:3b`. Sin Ollama, el asistente funciona solo con reglas.

Whisper necesita una GPU NVIDIA (CUDA 12). Las DLL de cuBLAS y cuDNN se
instalan con `requirements.txt`; el modelo se descarga solo la primera vez
(~1,6 GB `turbo`, ~480 MB `small`). Para ver el progreso:
`hf download mobiuslabsgmbh/faster-whisper-large-v3-turbo`.

Si PowerShell no deja activar el entorno:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## Uso

```powershell
python -m asistente                    # micrófono + voz (Enter para hablar)
python -m asistente --teclado          # escribes en vez de hablar
python -m asistente --texto            # imprime en vez de hablar
python -m asistente --teclado --texto  # como la fase 1 (sin modelos)
python -m asistente --whisper small    # Whisper más ligero (menos VRAM)
python -m asistente --sin-numa         # solo Enter (no escucha «Oye Numa»)
python -m asistente --sin-llm          # solo reglas, sin Ollama
python -m asistente --llm qwen3:4b     # otro modelo de Ollama
python -m asistente -v                 # muestra estados y latencias
```

Prueba: "Oye Numa, ¿qué hora es?" (o "Oye Numa", bip, y la orden), "pon un temporizador de 10 segundos",
"¿qué tiempo hace?", "cuéntame un chiste". Con LLM también: "¿necesito
paraguas?", "avísame en media hora", "¿cuál es la capital de Francia?".
Mientras Numa habla, «Oye Numa» la interrumpe y «Oye Numa, para» la calla.
Di `salir` para terminar.

## Estructura

| Ruta | Qué es |
|---|---|
| `asistente/__main__.py` | Bucle de eventos (consumidor) y arranque |
| `asistente/eventos.py` | Tipos de evento: `Activar`, `Frase`, `Aviso`, `Salir` |
| `asistente/entrada.py` | Hilo productor: teclado → eventos |
| `asistente/activacion.py` | Hilo productor: «Oye Numa» → eventos (VAD + Whisper) |
| `asistente/interrupcion.py` | Hilo productor: «Oye Numa» mientras habla → la corta |
| `asistente/estado.py` | Máquina de estados |
| `asistente/oido.py` | Contrato `Oido`: `OidoWhisper` (micrófono + VAD + Whisper) |
| `asistente/router.py` | Elige la skill para cada frase (regex: vía rápida) |
| `asistente/cerebro.py` | Elige la skill con el LLM si la regex no encaja |
| `asistente/voz.py` | Contrato `Voz`: `VozTexto` y `VozPiper` |
| `asistente/skills/` | Habilidades; `base.py` es el contrato |
| `experimentos/` | Pruebas sueltas de librerías, fuera del asistente |
| `modelos/` | Voces y modelos descargados (no se suben a git) |
| `tests/` | Tests; cuando pasan todos, la fase está terminada |
| `docs/diario.md` | Diario de desarrollo |
| `docs/adr/` | Decisiones de arquitectura |

## Fases

| # | Fase | Estado |
|---|---|---|
| 1 | Modo texto: router + skills (hora, temporizador, tiempo, chiste) | ✅ |
| 2 | Salida de voz con Piper | ✅ |
| 3 | Entrada de voz con faster-whisper + VAD (pulsar para hablar) | ✅ (afinando) |
| 4 | Palabra de activación «Oye Numa» (A: Whisper ✅ · B: openWakeWord) | ⏳ |
| 5 | Cerebro con LLM local (Ollama + salida estructurada) | ✅ |
| 6 | Pulido: interrupciones ✅, latencia, memoria corta | ⏳ |
| 7 | Satélite (Raspberry Pi) + servidor | |

## Pendientes

- [x] Revisar y aceptar el ADR 0002 (contrato `Voz`).
- [x] `HoraSkill`: decir la hora como una persona ("las seis menos doce").
- [x] Fase 3: entrada de voz.
- [x] Revisar y aceptar el ADR 0003 (contrato `Oido`).
- [ ] Ajustar el silencio de fin de frase (las pausas cortan la frase).
- [x] Eco: que los avisos del temporizador pasen por el bucle principal.
- [x] Revisar y aceptar el ADR 0004 (bucle de eventos).
- [x] Probar otras voces de Piper en español (me quedo con davefx).
- [ ] Revisar y aceptar el ADR 0005 («Oye Numa»).
- [ ] Medir falsos positivos de «Oye Numa» con tele o conversación.
- [x] Revisar y aceptar el ADR 0006 (cerebro con LLM).
- [ ] Revisar y aceptar el ADR 0007 (interrupciones).
