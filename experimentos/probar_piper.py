"""Experimento de la fase 2: Piper fuera del proyecto, para aprender la API.

No forma parte del asistente. Ejecuta desde la raíz del proyecto:

    python experimentos/probar_piper.py
    python experimentos/probar_piper.py "Hace 12 grados, despejado."

Mide tres cosas:
  - carga del modelo (se paga una vez, al arrancar el asistente)
  - tiempo hasta el primer trozo de audio (lo que el usuario PERCIBE)
  - RTF (real-time factor): tiempo de síntesis / duración del audio.
    RTF < 1 significa que sintetiza más rápido de lo que se tarda en oírlo.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
from piper import PiperVoice

MODELO = Path("modelos/es_ES-davefx-medium.onnx")
FRASE = (
    "Hola, soy tu asistente. ¿Qué le dice una iguana a su hermana gemela? "
    "Iguanita."
)


def main() -> None:
    texto = sys.argv[1] if len(sys.argv) > 1 else FRASE

    t0 = time.perf_counter()
    voz = PiperVoice.load(MODELO)  # CPU; la GPU la guardamos para Whisper/LLM
    print(f"Carga del modelo:     {(time.perf_counter() - t0) * 1000:6.0f} ms")

    t0 = time.perf_counter()
    trozos = []
    primer_trozo_ms = None
    for chunk in voz.synthesize(texto):  # generador: un trozo por frase
        if primer_trozo_ms is None:
            primer_trozo_ms = (time.perf_counter() - t0) * 1000
        trozos.append(np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16))
        frecuencia = chunk.sample_rate
    sintesis_s = time.perf_counter() - t0

    audio = np.concatenate(trozos)
    duracion_s = len(audio) / frecuencia
    print(f"Primer trozo:         {primer_trozo_ms:6.0f} ms")
    print(f"Síntesis completa:    {sintesis_s * 1000:6.0f} ms")
    print(f"Duración del audio:   {duracion_s * 1000:6.0f} ms  ({len(trozos)} trozos, {frecuencia} Hz)")
    print(f"RTF:                  {sintesis_s / duracion_s:6.2f}")

    sd.play(audio, frecuencia)  # vuelve enseguida; suena en segundo plano
    sd.wait()                   # bloquea hasta que termina


if __name__ == "__main__":
    main()
