"""Tests del productor de entrada: sin hilos ni teclado real."""
import queue

from asistente.eventos import Activar, Frase, Salir
from asistente.entrada import iniciar_entrada, producir_entrada


def lector(*lineas):
    """Simula input(): devuelve las líneas en orden y luego EOF (Ctrl+Z)."""
    pendientes = list(lineas)

    def leer():
        if not pendientes:
            raise EOFError
        return pendientes.pop(0)
    return leer


def vaciar(cola):
    eventos = []
    while not cola.empty():
        eventos.append(cola.get())
    return eventos


def test_modo_texto_publica_frases():
    cola = queue.Queue()
    producir_entrada(cola, con_texto=True, leer=lector("que hora es", "  ", "salir"))
    # La línea vacía se ignora; el EOF final se convierte en Salir.
    assert vaciar(cola) == [Frase("que hora es"), Frase("salir"), Salir()]


def test_modo_micro_cada_enter_es_activar():
    cola = queue.Queue()
    producir_entrada(cola, con_texto=False, leer=lector("", "lo que sea"))
    assert vaciar(cola) == [Activar(), Activar(), Salir()]


def test_si_el_hilo_falla_publica_salir():
    def roto():
        raise OSError("teclado desconectado")
    cola = queue.Queue()
    producir_entrada(cola, con_texto=True, leer=roto)
    assert vaciar(cola) == [Salir()]


def test_hilo_es_daemon_y_publica_en_la_cola():
    cola = queue.Queue()
    hilo = iniciar_entrada(cola, con_texto=True, leer=lector())  # EOF inmediato
    hilo.join(timeout=1)
    assert hilo.daemon
    assert cola.get(timeout=1) == Salir()
