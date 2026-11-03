"""Tests del contrato de voz (fase 2). VozPiper no se testea aquí: necesita
el modelo y un altavoz. Pruébala a mano (ver docs/diario.md)."""
import threading
import time

import pytest

from asistente.voz import Voz, VozTexto


def test_voz_es_abstracta():
    with pytest.raises(TypeError):
        Voz()


def test_voz_texto_imprime(capsys):
    VozTexto().decir("Hola")
    assert capsys.readouterr().out == "Hola\n"


def test_parar_por_defecto_no_hace_nada():
    VozTexto().parar()  # no debe lanzar


class VozLenta(Voz):
    """Simula un audio que tarda: registra cuándo empieza y acaba cada frase."""

    def __init__(self) -> None:
        super().__init__()
        self.eventos: list[str] = []

    def decir(self, texto: str) -> None:
        with self._lock:
            self.eventos.append(f"inicio {texto}")
            time.sleep(0.1)
            self.eventos.append(f"fin {texto}")


def test_dos_hilos_no_se_pisan():
    voz = VozLenta()
    hilos = [threading.Thread(target=voz.decir, args=(t,)) for t in ("a", "b")]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    # Cada "inicio" va seguido de SU "fin": nunca inicio a, inicio b, ...
    for i in range(0, 4, 2):
        assert voz.eventos[i].split()[1] == voz.eventos[i + 1].split()[1]
