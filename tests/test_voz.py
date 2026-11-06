"""Tests del contrato de voz (fase 2). VozPiper no se testea aquí: necesita
el modelo y un altavoz. Pruébala a mano (ver docs/diario.md)."""
import threading
import time

import pytest

from asistente.voz import Voz, VozTexto, tono


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


def test_pitar_en_texto(capsys):
    VozTexto().pitar()
    assert "🔔" in capsys.readouterr().out


def test_tono_sin_chasquidos():
    onda = tono()
    assert onda.dtype.name == "float32"
    assert abs(onda[0]) < 0.01 and abs(onda[-1]) < 0.01  # empieza y acaba en silencio
    assert abs(onda).max() <= 0.3 + 1e-6                  # respeta el volumen


def test_decir_frases_por_defecto_dice_cada_una(capsys):
    VozTexto().decir_frases(iter(["Primera.", "Segunda."]))
    assert capsys.readouterr().out == "Primera.\nSegunda.\n"


def test_decir_frases_consume_el_flujo_poco_a_poco():
    # Cada frase se dice ANTES de pedir la siguiente: así Piper habla
    # mientras el LLM sigue escribiendo.
    orden = []

    class VozApunta(Voz):
        def decir(self, texto):
            orden.append(f"dice {texto}")

    def flujo():
        for f in ("a", "b"):
            orden.append(f"llega {f}")
            yield f

    VozApunta().decir_frases(flujo())
    assert orden == ["llega a", "dice a", "llega b", "dice b"]
