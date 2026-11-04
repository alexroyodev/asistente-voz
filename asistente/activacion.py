"""Productor de activación por voz: "Oye Numa" (fase 4, paso A: VAD + Whisper).

Escucha el micrófono SIN PARAR en su propio hilo, corta lo que se dice en
trozos con el VAD, los transcribe y, si oye "Numa", publica un evento:

    "Oye Numa"                  → Activar()           (el asistente pita y escucha)
    "Oye Numa, ¿qué hora es?"   → Frase("que hora es") (directo al router)

Solo escucha cuando el hilo principal le da paso (`escuchando`, un Event que
el principal activa en REPOSO): así no se activa con la voz de Piper ni con
tu propia orden. Ver ADR 0005.

Paso B (pendiente): sustituir VAD + Whisper por un modelo openWakeWord
entrenado para "Oye Numa". El evento publicado será el mismo.
"""
from __future__ import annotations

import logging
import queue
import re
import threading
from typing import Callable, Iterable, Iterator

import numpy as np

from asistente.eventos import Activar, Evento, Frase
from asistente.oido import FRECUENCIA, UMBRAL_VOZ, VENTANA_VAD, fin_de_frase
from asistente.router import normalizar

log = logging.getLogger(__name__)

FRASE_ACTIVACION = "Oye Numa"  # también es la pista (hotwords) para Whisper
SILENCIO_SEGMENTO_S = 0.5      # más corto que en OidoWhisper: reaccionar rápido
SEGMENTO_MAX_S = 5.0
COLCHON_S = 0.5                # audio previo que se guarda para no cortar el inicio


# --- Funciones puras -------------------------------------------------------

def segmentar(bloques: Iterable[np.ndarray], vad,
              activo: Callable[[], bool] = lambda: True) -> Iterator[np.ndarray]:
    """Convierte un flujo continuo de audio en trozos con voz.

    Recibe bloques (de un micro o de un test) y devuelve cada frase en cuanto
    detecta el silencio que la cierra. Mientras `activo()` sea falso, descarta
    todo, para no juntar audio de antes y después de una pausa.
    """
    pendiente: list[np.ndarray] = []
    for bloque in bloques:
        if not activo():
            pendiente = []
            continue
        pendiente.append(bloque)
        audio = np.concatenate(pendiente)
        n = len(audio) // VENTANA_VAD * VENTANA_VAD
        probabilidades = np.ravel(vad(audio[:n])) if n else np.zeros(0)

        if not (probabilidades >= UMBRAL_VOZ).any():
            # Nadie habla: solo un colchón para no perder el arranque.
            pendiente = [audio[-int(COLCHON_S * FRECUENCIA):]]
            continue
        if fin_de_frase(probabilidades, silencio_s=SILENCIO_SEGMENTO_S) \
                or len(audio) / FRECUENCIA >= SEGMENTO_MAX_S:
            yield audio
            pendiente = []


def evento_para(texto: str | None) -> Evento | None:
    """Qué evento publicar para un texto transcrito (o None si no hay "numa")."""
    if not texto:
        return None
    m = re.search(r"\bnuma\b(.*)", normalizar(texto))
    if m is None:
        return None
    orden = m.group(1).strip()
    return Frase(orden) if orden else Activar()


# --- El productor ----------------------------------------------------------

def producir_activacion(cola: queue.Queue[Evento], bloques: Iterable[np.ndarray], vad,
                        transcribir: Callable[[np.ndarray], str | None],
                        escuchando: threading.Event) -> None:
    """Bucle del detector. Sin hilos ni micro: se testea con bloques falsos."""
    try:
        for audio in segmentar(bloques, vad, activo=escuchando.is_set):
            evento = evento_para(transcribir(audio))
            # Se comprueba otra vez: mientras transcribía, el principal puede
            # haber salido de REPOSO (p. ej. por un Enter).
            if evento is not None and escuchando.is_set():
                log.debug("Activación por voz: %r", evento)
                cola.put(evento)
    except Exception:
        # A diferencia del hilo de entrada, NO publicamos Salir(): sin
        # detector el asistente sigue funcionando con Enter.
        log.exception("El detector de 'Oye Numa' ha fallado; queda el Enter")


def _bloques_del_micro() -> Iterator[np.ndarray]:
    import sounddevice as sd

    bloques: queue.Queue[np.ndarray] = queue.Queue()
    with sd.InputStream(samplerate=FRECUENCIA, channels=1, dtype="float32",
                        blocksize=FRECUENCIA // 10,
                        callback=lambda datos, *_: bloques.put(datos[:, 0].copy())):
        while True:
            yield bloques.get()


def iniciar_activacion(cola: queue.Queue[Evento],
                       transcribir: Callable[[np.ndarray, str | None], str | None],
                       escuchando: threading.Event) -> threading.Thread:
    from faster_whisper.vad import get_vad_model

    hilo = threading.Thread(
        target=producir_activacion,
        args=(cola, _bloques_del_micro(), get_vad_model(),
              lambda audio: transcribir(audio, FRASE_ACTIVACION), escuchando),
        name="activacion", daemon=True,  # bloqueado en el micro: no se puede parar
    )
    hilo.start()
    return hilo
