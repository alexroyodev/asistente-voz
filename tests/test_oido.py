"""Tests del contrato de entrada (fase 3). OidoWhisper necesita micrófono y
GPU: se prueba a mano. Aquí se testea la lógica de decisión, que son
funciones puras."""
from dataclasses import dataclass

import numpy as np
import pytest

from asistente.oido import Oido, OidoTeclado, fin_de_frase, texto_fiable

# Una ventana de Silero son 32 ms: 0,8 s de silencio = 25 ventanas.
VOZ, SILENCIO = 0.9, 0.05


def test_oido_es_abstracto():
    with pytest.raises(TypeError):
        Oido()


def test_teclado_devuelve_texto(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "  que hora es  ")
    assert OidoTeclado().escuchar() == "que hora es"


def test_teclado_vacio_es_none(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "   ")
    assert OidoTeclado().escuchar() is None


# --- Fin de frase ---------------------------------------------------------

def test_sin_voz_no_es_fin():
    assert not fin_de_frase(np.full(100, SILENCIO))  # aún no ha empezado a hablar


def test_hablando_no_es_fin():
    assert not fin_de_frase(np.array([SILENCIO] * 5 + [VOZ] * 20))


def test_pausa_corta_no_es_fin():
    assert not fin_de_frase(np.array([VOZ] * 20 + [SILENCIO] * 10))  # 0,32 s


def test_silencio_largo_tras_hablar_es_fin():
    assert fin_de_frase(np.array([VOZ] * 20 + [SILENCIO] * 25))  # 0,8 s


def test_pausa_en_medio_no_cuenta():
    # Habla, pausa larga, vuelve a hablar: lo que cuenta es el ÚLTIMO silencio.
    probs = np.array([VOZ] * 10 + [SILENCIO] * 30 + [VOZ] * 10 + [SILENCIO] * 5)
    assert not fin_de_frase(probs)


# --- Filtro de alucinaciones ---------------------------------------------

@dataclass
class Segmento:
    text: str
    no_speech_prob: float


def test_texto_fiable_une_segmentos():
    segs = [Segmento(" Pon un temporizador", 0.1), Segmento(" de 5 minutos.", 0.2)]
    assert texto_fiable(segs) == "Pon un temporizador de 5 minutos."


def test_texto_fiable_descarta_no_voz():
    segs = [Segmento(" Qué hora es", 0.1), Segmento(" Gracias por ver el vídeo.", 0.9)]
    assert texto_fiable(segs) == "Qué hora es"


def test_texto_fiable_todo_descartado_es_none():
    assert texto_fiable([Segmento(" Subtítulos por la comunidad", 0.95)]) is None
    assert texto_fiable([]) is None
