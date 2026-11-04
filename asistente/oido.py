"""Entrada del asistente (fase 3): el espejo de `voz.py`.

El núcleo solo conoce el contrato `Oido`:
  - OidoWhisper: graba desde que se le llama hasta que el VAD detecta que te
    has callado, y transcribe con faster-whisper.

Quién decide CUÁNDO escuchar no es el Oido: es el evento Activar() (Enter
hoy, palabra de activación en la fase 4). Ver asistente/entrada.py.
Con --teclado no hay Oido: el texto llega ya hecho en un evento Frase.

Decisiones (ver ADR 0003):
  - `escuchar()` BLOQUEA hasta tener una frase y devuelve `str | None`.
    None = no se ha entendido nada (silencio, audio corto, alucinación
    descartada). No entender es NORMAL en voz: no es una excepción.
  - Fin de frase automático con Silero VAD (~0,8 s de silencio).
  - Tres capas contra alucinaciones: duración mínima, VAD de faster-whisper
    y descartar segmentos con `no_speech_prob` alto.
"""
from __future__ import annotations

import logging
import os
import queue
import time
from abc import ABC, abstractmethod
from typing import Iterable

import numpy as np

log = logging.getLogger(__name__)

FRECUENCIA = 16_000           # Whisper y Silero trabajan a 16 kHz, mono
VENTANA_VAD = 512             # muestras por ventana de Silero (32 ms)
UMBRAL_VOZ = 0.5              # probabilidad a partir de la cual es voz
SILENCIO_FIN_S = 0.8          # silencio tras hablar que da la frase por acabada
ESPERA_MAX_S = 5.0            # si no empiezas a hablar en este tiempo: None
FRASE_MAX_S = 15.0            # corte de seguridad
DURACION_MIN_S = 0.3          # menos que esto no es una frase
MAX_NO_SPEECH = 0.6           # segmentos más "no-voz" que esto se descartan


class Oido(ABC):
    @abstractmethod
    def escuchar(self) -> str | None:
        """Espera a que el usuario diga (o escriba) algo y lo devuelve.

        Bloquea. Devuelve None si no se ha entendido nada.
        """


# --- Funciones puras: la lógica de decisión, testeable sin micrófono -----

def fin_de_frase(probabilidades: np.ndarray, umbral: float = UMBRAL_VOZ,
                 silencio_s: float = SILENCIO_FIN_S) -> bool:
    """¿Ha hablado alguien y lleva `silencio_s` callado desde entonces?"""
    con_voz = np.flatnonzero(probabilidades >= umbral)
    if len(con_voz) == 0:
        return False  # todavía no ha empezado a hablar
    ventanas_silencio = len(probabilidades) - 1 - con_voz[-1]
    return ventanas_silencio * VENTANA_VAD / FRECUENCIA >= silencio_s


def texto_fiable(segmentos: Iterable, max_no_speech: float = MAX_NO_SPEECH) -> str | None:
    """Une los segmentos de Whisper descartando los que probablemente no son voz."""
    partes = [s.text.strip() for s in segmentos if s.no_speech_prob < max_no_speech]
    texto = " ".join(p for p in partes if p)
    return texto or None


# --- Implementación con micrófono ----------------------------------------

def _preparar_dlls_cuda() -> None:
    """Hace visibles las DLL de cuBLAS/cuDNN instaladas con pip (Windows)."""
    try:
        import nvidia.cublas
        import nvidia.cudnn
    except ImportError:
        return
    for paquete in (nvidia.cublas, nvidia.cudnn):
        carpeta = os.path.join(paquete.__path__[0], "bin")
        if os.path.isdir(carpeta):
            os.add_dll_directory(carpeta)
            os.environ["PATH"] = carpeta + os.pathsep + os.environ["PATH"]


class OidoWhisper(Oido):
    def __init__(self, modelo: str = "turbo") -> None:
        _preparar_dlls_cuda()
        # Importes aquí: con --teclado (y en los tests) no hacen falta.
        import sounddevice
        from faster_whisper import WhisperModel
        from faster_whisper.vad import get_vad_model

        self._sd = sounddevice
        self._whisper = WhisperModel(modelo, device="cuda", compute_type="int8_float16")
        self._vad = get_vad_model()

    def escuchar(self) -> str | None:
        audio = self._grabar_hasta_silencio()
        if audio is None or len(audio) / FRECUENCIA < DURACION_MIN_S:
            return None

        inicio = time.perf_counter()
        segmentos, _ = self._whisper.transcribe(
            audio, language="es", beam_size=1, vad_filter=True,
        )
        texto = texto_fiable(segmentos)  # aquí se transcribe (es un generador)
        log.debug("Transcrito en %.0f ms: %r",
                  (time.perf_counter() - inicio) * 1000, texto)
        if texto:
            print(f"  🎙  {texto}")
        return texto

    def _grabar_hasta_silencio(self) -> np.ndarray | None:
        # El callback corre en el hilo de audio de sounddevice; Queue es
        # segura entre hilos, así que no hace falta Lock.
        bloques: queue.Queue[np.ndarray] = queue.Queue()

        def al_recibir(datos, frames, tiempo, estado):
            bloques.put(datos[:, 0].copy())

        grabado: list[np.ndarray] = []
        inicio = time.perf_counter()
        print("  🎙  Escuchando...")
        with self._sd.InputStream(samplerate=FRECUENCIA, channels=1, dtype="float32",
                                  blocksize=FRECUENCIA // 10, callback=al_recibir):
            while True:
                grabado.append(bloques.get())  # bloquea hasta el siguiente trozo (100 ms)
                audio = np.concatenate(grabado)
                n = len(audio) // VENTANA_VAD * VENTANA_VAD
                probabilidades = np.ravel(self._vad(audio[:n]))
                transcurrido = time.perf_counter() - inicio

                if fin_de_frase(probabilidades):
                    return audio
                if transcurrido > ESPERA_MAX_S and not (probabilidades >= UMBRAL_VOZ).any():
                    log.debug("Nadie ha hablado en %.0f s", ESPERA_MAX_S)
                    return None
                if transcurrido > FRASE_MAX_S:
                    log.debug("Frase cortada a los %.0f s", FRASE_MAX_S)
                    return audio
