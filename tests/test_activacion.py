"""Tests del detector de "Oye Numa", sin micrófono, sin Whisper y sin Silero:
un VAD falso decide "hay voz" por el volumen."""
import queue
import threading

import numpy as np
import pytest

from asistente.activacion import evento_para, producir_activacion, segmentar
from asistente.eventos import Activar, Frase

BLOQUE = 1600  # 100 ms a 16 kHz


def vad_falso(audio):
    """Una probabilidad por ventana de 512: 1 si hay volumen, 0 si es silencio."""
    return (np.abs(audio.reshape(-1, 512)).max(axis=1) > 0.1).astype(float)


def flujo(*partes):
    """partes: ("voz", segundos) o ("silencio", segundos) → bloques de 100 ms."""
    audio = np.concatenate([
        np.full(int(s * 16000), 0.5 if tipo == "voz" else 0.0, np.float32)
        for tipo, s in partes
    ])
    return [audio[i:i + BLOQUE] for i in range(0, len(audio), BLOQUE)]


# --- evento_para ----------------------------------------------------------

@pytest.mark.parametrize("texto, esperado", [
    ("Oye Numa", Activar()),
    ("Oye Numa.", Activar()),
    ("Numa", Activar()),
    ("Oye Numa, ¿qué hora es?", Frase("que hora es")),
    ("Oye, Numa, cuéntame un chiste.", Frase("cuentame un chiste")),
    ("¿Qué tiempo hace?", None),
    ("Hoy he visto la luna", None),
    ("Es numérico", None),      # "numa" tiene que ser una palabra entera
    (None, None),
])
def test_evento_para(texto, esperado):
    assert evento_para(texto) == esperado


# --- segmentar ------------------------------------------------------------

def test_segmenta_cada_frase():
    bloques = flujo(("silencio", 1), ("voz", 1), ("silencio", 1),
                    ("voz", 0.6), ("silencio", 1))
    trozos = list(segmentar(bloques, vad_falso))
    assert len(trozos) == 2


def test_silencio_no_produce_trozos():
    assert list(segmentar(flujo(("silencio", 3)), vad_falso)) == []


def test_pausado_descarta_todo():
    bloques = flujo(("voz", 1), ("silencio", 1))
    assert list(segmentar(bloques, vad_falso, activo=lambda: False)) == []


# --- producir_activacion --------------------------------------------------

def correr(textos, escuchando=True):
    """Ejecuta el detector con una transcripción falsa que devuelve `textos`."""
    pendientes = list(textos)
    evento = threading.Event()
    if escuchando:
        evento.set()
    cola = queue.Queue()
    bloques = flujo(*[p for _ in textos for p in (("voz", 1), ("silencio", 1))])
    producir_activacion(cola, bloques, vad_falso, lambda audio: pendientes.pop(0), evento)
    eventos = []
    while not cola.empty():
        eventos.append(cola.get())
    return eventos


def test_publica_activar_y_frase():
    assert correr(["Oye Numa", "hola", "Oye Numa, qué hora es"]) == \
        [Activar(), Frase("que hora es")]


def test_en_pausa_no_publica():
    assert correr(["Oye Numa"], escuchando=False) == []


def test_si_la_transcripcion_falla_no_revienta():
    def rota(audio):
        raise RuntimeError("GPU sin memoria")
    cola, evento = queue.Queue(), threading.Event()
    evento.set()
    producir_activacion(cola, flujo(("voz", 1), ("silencio", 1)), vad_falso, rota, evento)
    assert cola.empty()  # registra el error y termina, sin publicar Salir
