"""Experimento de la fase 3: faster-whisper con tu micrófono (pulsar para hablar).

No forma parte del asistente. Ejecuta desde la raíz del proyecto:

    python experimentos/probar_whisper.py            # modelo small
    python experimentos/probar_whisper.py turbo      # large-v3-turbo
    python experimentos/probar_whisper.py base --cpu

Enter para empezar a grabar, Enter para parar. Línea vacía + "q" para salir.
La primera vez descarga el modelo (puede tardar varios minutos).

Mide: duración de lo grabado, tiempo de transcripción y VRAM ocupada.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time


def preparar_dlls_cuda() -> None:
    """Hace visibles las DLL de cuBLAS/cuDNN instaladas con pip (Windows)."""
    try:
        import nvidia.cublas
        import nvidia.cudnn
    except ImportError:
        return  # sin las librerías: solo funcionará en CPU
    for paquete in (nvidia.cublas, nvidia.cudnn):
        carpeta = os.path.join(paquete.__path__[0], "bin")
        os.add_dll_directory(carpeta)
        os.environ["PATH"] = carpeta + os.pathsep + os.environ["PATH"]


preparar_dlls_cuda()

import numpy as np  # noqa: E402
import sounddevice as sd  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402

FRECUENCIA = 16_000  # Whisper trabaja a 16 kHz, mono


def vram_usada() -> str:
    try:
        salida = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        return salida.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "?"


def grabar() -> np.ndarray:
    """Graba desde que se pulsa Enter hasta el siguiente Enter."""
    trozos: list[np.ndarray] = []

    def al_recibir(datos, frames, tiempo, estado):  # se llama desde OTRO hilo
        trozos.append(datos.copy())

    with sd.InputStream(samplerate=FRECUENCIA, channels=1, dtype="float32",
                        callback=al_recibir):
        input("  🎙  Grabando... (Enter para parar)")
    return np.concatenate(trozos)[:, 0] if trozos else np.zeros(0, np.float32)


def main() -> None:
    nombre = next((a for a in sys.argv[1:] if not a.startswith("-")), "small")
    en_cpu = "--cpu" in sys.argv
    dispositivo, tipo = ("cpu", "int8") if en_cpu else ("cuda", "int8_float16")

    print(f"VRAM antes de cargar: {vram_usada()}")
    t0 = time.perf_counter()
    modelo = WhisperModel(nombre, device=dispositivo, compute_type=tipo)
    print(f"Modelo {nombre} ({dispositivo}, {tipo}) cargado en "
          f"{time.perf_counter() - t0:.1f} s · VRAM: {vram_usada()}")

    while True:
        if input("\nEnter para hablar (q + Enter para salir): ").strip().lower() == "q":
            break
        audio = grabar()
        duracion = len(audio) / FRECUENCIA
        if duracion < 0.3:
            print("  (demasiado corto)")
            continue

        t0 = time.perf_counter()
        segmentos, info = modelo.transcribe(
            audio,
            language="es",       # fijarlo evita detectar idioma: más rápido
            beam_size=1,         # búsqueda voraz: más rápido, casi igual de bueno
            vad_filter=True,     # Silero VAD recorta silencios y evita "alucinar"
        )
        texto = "".join(s.text for s in segmentos).strip()  # aquí se transcribe
        ms = (time.perf_counter() - t0) * 1000
        print(f"  {duracion:.1f} s de audio → {ms:.0f} ms  ·  {texto!r}")


if __name__ == "__main__":
    main()
