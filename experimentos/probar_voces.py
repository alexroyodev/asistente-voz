"""Experimento: comparar las voces de Piper en español con la misma frase.

No forma parte del asistente. Ejecuta desde la raíz del proyecto:

    python experimentos/probar_voces.py                      # todas las voces
    python experimentos/probar_voces.py es_AR-daniela-high   # solo algunas
    python experimentos/probar_voces.py --velocidad 0.9 --variacion 0.8

Descarga en modelos/ las voces que falten (60-120 MB cada una).
Tras cada voz: Enter = siguiente · r = repetir · q = salir.

Parámetros (Piper los llama así):
  --velocidad  length_scale: <1 más rápido, >1 más lento (por defecto, el de la voz)
  --variacion  noise_scale: más alto = entonación más viva, más bajo = más plana
"""
from __future__ import annotations

import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
from piper import PiperVoice, SynthesisConfig

CARPETA = Path("modelos")
VOCES = [
    "es_ES-davefx-medium",      # la actual
    "es_ES-sharvard-medium",    # dos hablantes: se prueban los dos
    "es_ES-carlfm-x_low",
    "es_ES-mls_9972-low",
    "es_ES-mls_10246-low",
    "es_MX-ald-medium",
    "es_MX-claude-high",
    "es_AR-daniela-high",
]
FRASE = (
    "Son las 6 menos 12 de la tarde. "
    "¿Qué hace una abeja en el gimnasio? Zum-ba. "
    "Temporizador de 5 minutos en marcha."
)


def opcion_float(nombre: str) -> float | None:
    if nombre in sys.argv:
        return float(sys.argv[sys.argv.index(nombre) + 1])
    return None


def asegurar_voz(nombre: str) -> Path:
    modelo = CARPETA / f"{nombre}.onnx"
    if not modelo.exists():
        print(f"  ↓ Descargando {nombre}...")
        subprocess.run(
            [sys.executable, "-m", "piper.download_voices", nombre, "--data-dir", str(CARPETA)],
            check=True,
        )
    return modelo


def sintetizar(voz: PiperVoice, config: SynthesisConfig) -> tuple[np.ndarray, int, float]:
    inicio = time.perf_counter()
    trozos, frecuencia = [], 22050
    for chunk in voz.synthesize(FRASE, syn_config=config):
        trozos.append(np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16))
        frecuencia = chunk.sample_rate
    return np.concatenate(trozos), frecuencia, time.perf_counter() - inicio


def main() -> None:
    # En Windows, si la salida se redirige, Python usa cp1252 y "▶" no existe.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    elegidas =[a for a in sys.argv[1:] if a.startswith("es_")] or VOCES
    velocidad = opcion_float("--velocidad")
    variacion = opcion_float("--variacion")
    print(f"Frase: {FRASE!r}\n")

    for nombre in elegidas:
        voz = PiperVoice.load(asegurar_voz(nombre))
        # Las voces con varios hablantes se prueban con cada uno.
        hablantes = range(voz.config.num_speakers) if voz.config.num_speakers > 1 else [None]
        for hablante in hablantes:
            config = SynthesisConfig(speaker_id=hablante, length_scale=velocidad,
                                     noise_scale=variacion)
            audio, frecuencia, segundos = sintetizar(voz, config)
            etiqueta = nombre if hablante is None else f"{nombre} (hablante {hablante})"
            while True:
                print(f"▶ {etiqueta}  ·  {frecuencia} Hz  ·  síntesis {segundos * 1000:.0f} ms")
                sd.play(audio, frecuencia)
                sd.wait()
                tecla = input("  Enter = siguiente · r = repetir · g = guardar wav · q = salir: ")
                tecla = tecla.strip().lower()
                if tecla == "q":
                    return
                if tecla == "g":
                    destino = Path(f"{etiqueta.replace(' ', '_').replace('(', '').replace(')', '')}.wav")
                    with wave.open(str(destino), "wb") as w:
                        w.setnchannels(1)
                        w.setsampwidth(2)
                        w.setframerate(frecuencia)
                        w.writeframes(audio.tobytes())
                    print(f"  💾 Guardado en {destino}")
                    continue
                if tecla != "r":
                    break


if __name__ == "__main__":
    main()
