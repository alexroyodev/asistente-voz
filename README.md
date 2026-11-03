# Asistente de voz propio

Asistente estilo Alexa construido desde el núcleo, como proyecto de
aprendizaje. Local, privado y en español.

## Arquitectura (objetivo)

```
micrófono → wake word → VAD → voz a texto → router / LLM → skills → texto a voz → altavoz
                         └──────────── máquina de estados ────────────┘
```

## Puesta en marcha (Windows, PowerShell)

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest         # al principio fallan 4 tests: son tus TODO(human)
python -m asistente -v    # modo texto
```

Si PowerShell no deja activar el entorno:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## Estructura

| Ruta | Qué es |
|---|---|
| `asistente/__main__.py` | Bucle principal (modo texto) |
| `asistente/estado.py` | Máquina de estados |
| `asistente/router.py` | Elige la skill para cada frase |
| `asistente/skills/` | Habilidades; `base.py` es el contrato |
| `tests/` | Tests; cuando pasan todos, la fase está terminada |
| `docs/diario.md` | Diario de desarrollo |
| `docs/adr/` | Decisiones de arquitectura |

## Fase 1: tus tareas

- [ ] `estado.py`: validar transiciones
- [ ] `skills/temporizador.py`: temporizador que no bloquea
- [ ] `skills/tiempo.py`: consulta a Open-Meteo con manejo de errores
- [ ] Reto extra: una skill nueva a tu gusto (chiste, fecha, calculadora…)
