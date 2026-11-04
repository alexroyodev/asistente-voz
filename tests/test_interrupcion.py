"""Tests del detector de interrupciones: sin micro, sin Whisper y sin Piper."""
import queue
import threading

import numpy as np
import pytest

from asistente.eventos import Activar
from asistente.interrupcion import (
    UMBRAL_RMS, Ventanas, decidir, nivel, producir_interrupciones,
)

BLOQUE = 1600  # 100 ms a 16 kHz
PIPER, TU = 0.003, 0.12  # amplitudes parecidas a las medidas


def bloques(*partes):
    """partes: (amplitud, segundos) → bloques de 100 ms de una senoide."""
    audio = np.concatenate([
        (a * np.sqrt(2) * np.sin(np.arange(int(s * 16000)) * 0.3)).astype(np.float32)
        for a, s in partes
    ])  # √2: el RMS de la senoide es justo `a`
    return [audio[i:i + BLOQUE] for i in range(0, len(audio), BLOQUE)]


# --- nivel ----------------------------------------------------------------

def test_nivel_mide_el_tramo_mas_fuerte():
    # 0,5 s de tu voz dentro de 2 s de Piper: la media la diluiría.
    ventana = np.concatenate(bloques((PIPER, 0.75), (TU, 0.5), (PIPER, 0.75)))
    assert nivel(ventana) == pytest.approx(TU, rel=0.05)
    # La media de los 2 s diluye tu voz a la mitad (√(0,5 s / 2 s) = 0,5).
    assert float(np.sqrt(np.mean(ventana ** 2))) == pytest.approx(TU / 2, rel=0.05)


def test_nivel_de_piper_queda_bajo_el_umbral():
    assert nivel(np.concatenate(bloques((PIPER, 2)))) < UMBRAL_RMS


# --- decidir --------------------------------------------------------------

@pytest.mark.parametrize("texto, esperado", [
    ("Oye Numa", (True, Activar())),
    ("Oye Numa, ¿qué hora es?", (True, Activar())),  # la orden puede venir cortada
    ("Oye Numa, que", (True, Activar())),
    ("Oye Numa, para", (True, None)),
    ("Oye Numa, cállate ya", (True, None)),
    ("Oye Numa, silencio.", (True, None)),
    ("Oye Numa, para cuándo es el examen", (True, None)),  # limitación conocida
    ("Hoy hace un día estupendo", (False, None)),
    (None, (False, None)),
])
def test_decidir(texto, esperado):
    assert decidir(texto) == esperado


# --- Ventanas -------------------------------------------------------------

def test_ventanas_cada_paso_con_solape():
    v = Ventanas(ventana_s=2.0, paso_s=0.75)
    entregadas = [v.añadir(b) for b in bloques((TU, 3))]
    llenas = [w for w in entregadas if w is not None]
    assert len(llenas) == 4                       # a los 0,8 · 1,5 · 2,3 · 3,0 s
    assert all(len(w) <= 2 * 16000 for w in llenas)


def test_reiniciar_olvida_el_audio():
    v = Ventanas(paso_s=0.75)
    for b in bloques((TU, 0.7)):
        v.añadir(b)
    v.reiniciar()
    assert all(v.añadir(b) is None for b in bloques((TU, 0.7)))


# --- producir_interrupciones ----------------------------------------------

def correr(partes, textos, hablando=True):
    pendientes = list(textos)
    paradas, cola, evento = [], queue.Queue(), threading.Event()
    if hablando:
        evento.set()

    def transcribir(audio):
        return pendientes.pop(0) if pendientes else ""

    producir_interrupciones(cola, bloques(*partes), transcribir, evento,
                            parar=lambda: paradas.append("parar"))
    eventos = []
    while not cola.empty():
        eventos.append(cola.get())
    return paradas, eventos, pendientes


def test_piper_solo_no_se_transcribe_ni_interrumpe():
    paradas, eventos, pendientes = correr([(PIPER, 5)], ["Oye Numa"])
    assert paradas == [] and eventos == []
    assert pendientes == ["Oye Numa"]  # ni se llegó a transcribir: ahorra GPU


def test_tu_voz_interrumpe_y_publica_activar():
    paradas, eventos, _ = correr([(PIPER, 1), (TU, 0.6), (PIPER, 2)], ["Oye Numa"])
    assert paradas == ["parar"] and eventos == [Activar()]


def test_oye_numa_para_solo_calla():
    paradas, eventos, _ = correr([(PIPER, 1), (TU, 0.6), (PIPER, 2)], ["Oye Numa, para"])
    assert paradas == ["parar"] and eventos == []


def test_no_interrumpe_dos_veces_la_misma_frase():
    # Las ventanas se solapan y tu frase sigue tras el corte: sin periodo
    # refractario, se interrumpiría también la respuesta siguiente.
    paradas, eventos, _ = correr([(PIPER, 1), (TU, 1.5), (PIPER, 2)],
                                 ["Oye Numa", "Oye Numa, que hora es", "Oye Numa"])
    assert paradas == ["parar"] and eventos == [Activar()]


def test_tras_el_refractario_vuelve_a_escuchar():
    paradas, eventos, _ = correr([(PIPER, 1), (TU, 0.6), (PIPER, 3), (TU, 0.6), (PIPER, 1)],
                                 ["Oye Numa", "Oye Numa, para"])
    assert paradas == ["parar", "parar"] and eventos == [Activar()]


def test_sin_hablar_no_escucha():
    paradas, eventos, _ = correr([(TU, 3)], ["Oye Numa"], hablando=False)
    assert paradas == [] and eventos == []
