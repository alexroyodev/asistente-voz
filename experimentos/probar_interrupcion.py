"""Experimento de la fase 6: ¿se puede interrumpir a Piper diciendo "Oye Numa"?

No forma parte del asistente. Ejecuta desde la raíz del proyecto:

    python experimentos/probar_interrupcion.py          # con altavoces
    python experimentos/probar_interrupcion.py --nadie  # no digas nada: ¿se activa solo?
    python experimentos/probar_interrupcion.py --umbral 0   # sin puerta de volumen

Piper lee un texto largo por los altavoces. A la vez, cada 1,5 s se
transcriben los ÚLTIMOS 2 s del micrófono (ventanas solapadas: no se espera
a ningún silencio, porque mientras Piper habla no lo hay). Di "Oye Numa" a
mitad: si lo detecta, corta a Piper.

Mide: si te oye por encima de Piper, cuánto tarda en cortar desde que lo
dices, y si Piper se activa a sí mismo (falsos positivos sin hablar).
"""
from __future__ import annotations

import queue
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # para importar asistente

from asistente.activacion import FRASE_ACTIVACION, evento_para  # noqa: E402
from asistente.oido import FRECUENCIA, _preparar_dlls_cuda  # noqa: E402

_preparar_dlls_cuda()

import numpy as np  # noqa: E402

VENTANA_S = 2.0   # cuánto audio se transcribe cada vez
PASO_S = 1.5      # cada cuánto (solape de 0,5 s: "Oye Numa" no cae partido)
# Puerta de volumen: Piper llega al micro muy débil (RMS medio ~0,0007, pico
# ~0,01 medido en este portátil); tu voz, mucho más fuerte. Las ventanas por
# debajo ni se transcriben: con audio débil, la pista hace alucinar "Oye Numa".
UMBRAL_RMS = 0.005
TEXTO = (
    "Hoy hace un día estupendo en Madrid, con cielos despejados y una temperatura "
    "máxima de veintidós grados. Por la tarde se esperan algunas nubes, pero no "
    "lloverá. Mañana bajarán las temperaturas y soplará viento del norte, así que "
    "conviene llevar una chaqueta si vas a salir temprano. El fin de semana volverá "
    "el buen tiempo, ideal para dar un paseo por el parque o quedar con amigos. "
    "Recuerda beber agua y protegerte del sol en las horas centrales del día."
)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import sounddevice as sd
    from faster_whisper import WhisperModel
    from piper import PiperVoice

    print("Cargando Piper y Whisper...")
    voz = PiperVoice.load("modelos/es_ES-davefx-medium.onnx")
    whisper = WhisperModel("turbo", device="cuda", compute_type="int8_float16")
    trozos = [np.frombuffer(c.audio_int16_bytes, np.int16) for c in voz.synthesize(TEXTO)]
    audio = np.concatenate(trozos)
    duracion = len(audio) / 22050
    sin_hablar = "--nadie" in sys.argv
    umbral = float(sys.argv[sys.argv.index("--umbral") + 1]) if "--umbral" in sys.argv \
        else UMBRAL_RMS
    print(f"Piper va a hablar {duracion:.0f} s. "
          + ("NO digas nada: medimos si se activa solo." if sin_hablar
             else "Di «Oye Numa» cuando quieras (y apunta el segundo en que lo dices)."))
    time.sleep(1)

    grabado: queue.Queue[np.ndarray] = queue.Queue()
    microfono: list[np.ndarray] = []
    inicio = time.perf_counter()
    sd.play(audio, 22050)  # no bloquea: suena de fondo
    with sd.InputStream(samplerate=FRECUENCIA, channels=1, dtype="float32",
                        blocksize=FRECUENCIA // 10,
                        callback=lambda d, *_: grabado.put(d[:, 0].copy())):
        siguiente = PASO_S
        while (t := time.perf_counter() - inicio) < duracion + 1:
            while not grabado.empty():
                microfono.append(grabado.get())
            if t < siguiente:
                time.sleep(0.05)
                continue
            siguiente += PASO_S
            ventana = np.concatenate(microfono)[-int(VENTANA_S * FRECUENCIA):]
            # El pico de los 100 ms más fuertes: la media de 2 s diluiría un
            # "Oye Numa" corto rodeado de murmullo de Piper.
            nivel = max(float(np.sqrt(np.mean(b ** 2))) for b in np.array_split(ventana, 20))
            if nivel < umbral:
                print(f"  {t:5.1f} s · nivel {nivel:.4f} · (por debajo del umbral: no se transcribe)")
                continue
            t0 = time.perf_counter()
            segmentos, _ = whisper.transcribe(ventana, language="es", beam_size=1,
                                              hotwords=FRASE_ACTIVACION)
            texto = "".join(s.text for s in segmentos).strip()
            ms = (time.perf_counter() - t0) * 1000
            evento = evento_para(texto)
            print(f"  {t:5.1f} s · nivel {nivel:.4f} · {ms:4.0f} ms · "
                  f"{'✅ NUMA' if evento else '      '} {texto!r}")
            if evento is not None:
                sd.stop()
                print(f"\n⏹  Piper cortado a los {time.perf_counter() - inicio:.1f} s. "
                      "Resta el segundo en que dijiste «Oye Numa»: eso es la latencia.")
                return
    sd.stop()
    print("\nPiper terminó sin interrupciones"
          + (" (bien: no se activó solo)." if sin_hablar else " (no te detectó)."))


if __name__ == "__main__":
    main()
