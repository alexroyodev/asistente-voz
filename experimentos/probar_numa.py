"""Experimento de la fase 4 (paso A): detectar "Oye Numa" con VAD + Whisper.

No forma parte del asistente. Ejecuta desde la raíz del proyecto:

    python experimentos/probar_numa.py              # turbo, con pista "Numa"
    python experimentos/probar_numa.py small        # modelo más ligero
    python experimentos/probar_numa.py --sin-pista  # sin sesgar a Whisper

Escucha SIN PARAR (no hay que pulsar nada). Cada vez que dices algo y te
callas ~0,5 s, transcribe ese trozo y muestra si ha detectado "numa".
Ctrl+C para salir.

Objetivo: averiguar CÓMO escribe Whisper "Oye Numa" (Numa, Nuna, Luma...),
cuánto tarda y cuántas falsas detecciones hay hablando de otras cosas.
"""
from __future__ import annotations

import queue
import re
import sys
import time
from pathlib import Path
from typing import Iterable, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # para importar asistente

from asistente.oido import (  # noqa: E402
    FRECUENCIA, UMBRAL_VOZ, VENTANA_VAD, _preparar_dlls_cuda, fin_de_frase,
)
from asistente.router import normalizar  # noqa: E402

_preparar_dlls_cuda()

import numpy as np  # noqa: E402

SILENCIO_SEGMENTO_S = 0.5   # más corto que en OidoWhisper: queremos reaccionar rápido
SEGMENTO_MAX_S = 5.0
COLCHON_S = 0.5             # audio previo que se conserva para no cortar el inicio


def segmentar(bloques: Iterable[np.ndarray], vad) -> Iterator[np.ndarray]:
    """Convierte un flujo continuo de audio en trozos con voz.

    Sin micrófono ni hilos: recibe bloques (de un micro o de un test) y
    devuelve cada frase en cuanto detecta el silencio que la cierra.
    """
    pendiente: list[np.ndarray] = []
    for bloque in bloques:
        pendiente.append(bloque)
        audio = np.concatenate(pendiente)
        n = len(audio) // VENTANA_VAD * VENTANA_VAD
        probabilidades = np.ravel(vad(audio[:n])) if n else np.zeros(0)

        if not (probabilidades >= UMBRAL_VOZ).any():
            # Nadie habla: solo guardamos un colchón para no perder el arranque.
            pendiente = [audio[-int(COLCHON_S * FRECUENCIA):]]
            continue
        if fin_de_frase(probabilidades, silencio_s=SILENCIO_SEGMENTO_S) \
                or len(audio) / FRECUENCIA >= SEGMENTO_MAX_S:
            yield audio
            pendiente = []


def detectar_numa(texto: str) -> tuple[bool, str]:
    """¿Contiene "numa"? Devuelve (detectado, lo que va detrás)."""
    m = re.search(r"\bnuma\b(.*)", normalizar(texto))
    return (True, m.group(1).strip()) if m else (False, "")


def bloques_del_micro(sd) -> Iterator[np.ndarray]:
    cola: queue.Queue[np.ndarray] = queue.Queue()
    with sd.InputStream(samplerate=FRECUENCIA, channels=1, dtype="float32",
                        blocksize=FRECUENCIA // 10,
                        callback=lambda datos, *_: cola.put(datos[:, 0].copy())):
        while True:
            yield cola.get()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import sounddevice as sd
    from faster_whisper import WhisperModel
    from faster_whisper.vad import get_vad_model

    nombre = next((a for a in sys.argv[1:] if not a.startswith("-")), "turbo")
    # hotwords: sesga a Whisper hacia escribir "Numa" (una palabra que no conoce).
    pista = None if "--sin-pista" in sys.argv else "Oye Numa"
    whisper = WhisperModel(nombre, device="cuda", compute_type="int8_float16")
    vad = get_vad_model()
    print(f"Whisper {nombre} · pista: {pista!r}. Habla cuando quieras (Ctrl+C para salir).\n")

    detecciones = trozos = 0
    try:
        for audio in segmentar(bloques_del_micro(sd), vad):
            inicio = time.perf_counter()
            segmentos, _ = whisper.transcribe(audio, language="es", beam_size=1,
                                              vad_filter=True, hotwords=pista)
            texto = "".join(s.text for s in segmentos).strip()
            ms = (time.perf_counter() - inicio) * 1000
            if not texto:
                continue
            trozos += 1
            detectado, resto = detectar_numa(texto)
            detecciones += detectado
            marca = "✅ NUMA" if detectado else "  ·   "
            extra = f"  → orden: {resto!r}" if resto else ""
            print(f"{marca} {len(audio) / FRECUENCIA:4.1f} s · {ms:4.0f} ms · {texto!r}{extra}")
    except KeyboardInterrupt:
        pass
    print(f"\n{trozos} trozos transcritos, {detecciones} con 'numa'.")


if __name__ == "__main__":
    main()
