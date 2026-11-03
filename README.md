# Asistente de voz propio

Asistente estilo Alexa construido desde el núcleo, como proyecto de
aprendizaje. Local, privado y en español.

## Arquitectura

Objetivo final:

```
micrófono → wake word → VAD → voz a texto → router / LLM → skills → texto a voz → altavoz
                         └──────────── máquina de estados ────────────┘
```

Hoy (fase 3): pulsas Enter, hablas, y el asistente responde hablando.

```
micrófono → VAD (fin de frase) → Whisper → router → skill → Voz (Piper) → altavoz
   └─────────────── Oido ──────────────┘                    └──── Voz ────┘
                         └──────────── máquina de estados ────────────┘
```

El centro (estados, router, skills) no cambia entre fases; lo que cambia son
los extremos, cada uno detrás de una interfaz propia (`Oido`, `Skill`, `Voz`).

## Puesta en marcha (Windows, PowerShell)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m piper.download_voices es_ES-davefx-medium --data-dir modelos
python -m pytest
```

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
python -m asistente -v                 # muestra estados y latencias
```

Prueba: "¿qué hora es?", "pon un temporizador de 10 segundos",
"¿qué tiempo hace?", "cuéntame un chiste". Di `salir` para terminar.

## Estructura

| Ruta | Qué es |
|---|---|
| `asistente/__main__.py` | Bucle principal y elección de voz |
| `asistente/estado.py` | Máquina de estados |
| `asistente/oido.py` | Contrato `Oido`: `OidoTeclado` y `OidoWhisper` |
| `asistente/router.py` | Elige la skill para cada frase |
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
| 4 | Palabra de activación con openWakeWord | |
| 5 | Cerebro con LLM local (Ollama + tool calling) | |
| 6 | Pulido: interrupciones, latencia, memoria corta | |
| 7 | Satélite (Raspberry Pi) + servidor | |

## Pendientes

- [x] Revisar y aceptar el ADR 0002 (contrato `Voz`).
- [x] `HoraSkill`: decir la hora como una persona ("las seis menos doce").
- [x] Fase 3: entrada de voz.
- [ ] Revisar y aceptar el ADR 0003 (contrato `Oido`).
- [ ] Ajustar el silencio de fin de frase (las pausas cortan la frase).
- [ ] Eco: que los avisos del temporizador pasen por el bucle principal.
