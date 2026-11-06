"""Tests de la memoria corta, con un reloj falso que se adelanta a mano."""
from asistente.conversacion import Conversacion, Turno


class Reloj:
    def __init__(self):
        self.ahora = 1000.0

    def __call__(self):
        return self.ahora


def test_recuerda_los_ultimos_turnos_en_orden():
    c = Conversacion(turnos=3, reloj=Reloj())
    for i in range(1, 5):
        c.anotar(f"pregunta {i}", f"respuesta {i}")
    assert [t.usuario for t in c.turnos()] == ["pregunta 2", "pregunta 3", "pregunta 4"]


def test_mensajes_en_formato_chat():
    c = Conversacion(reloj=Reloj())
    c.anotar("Háblame de Roma", "Roma se fundó en el 753 a.C.")
    assert c.mensajes() == [
        {"role": "user", "content": "Háblame de Roma"},
        {"role": "assistant", "content": "Roma se fundó en el 753 a.C."},
    ]


def test_resumen_en_texto():
    c = Conversacion(reloj=Reloj())
    c.anotar("pon un temporizador de 5 minutos", "Temporizador de 5 minutos en marcha.")
    assert c.resumen() == ("Usuario: pon un temporizador de 5 minutos\n"
                           "Numa: Temporizador de 5 minutos en marcha.")


def test_caduca_tras_un_rato_sin_hablar():
    reloj = Reloj()
    c = Conversacion(caduca_s=120, reloj=reloj)
    c.anotar("Háblame de Roma", "Roma...")
    reloj.ahora += 119
    assert len(c.turnos()) == 1          # aún no
    reloj.ahora += 2
    assert c.turnos() == []              # 121 s: olvidado
    assert c.mensajes() == [] and c.resumen() == ""


def test_cada_turno_renueva_el_plazo():
    reloj = Reloj()
    c = Conversacion(caduca_s=120, reloj=reloj)
    c.anotar("uno", "1")
    reloj.ahora += 100
    c.anotar("dos", "2")                 # a los 100 s: el plazo vuelve a empezar
    reloj.ahora += 100
    assert [t.usuario for t in c.turnos()] == ["uno", "dos"]


def test_tras_caducar_empieza_de_cero():
    reloj = Reloj()
    c = Conversacion(caduca_s=120, reloj=reloj)
    c.anotar("tema viejo", "...")
    reloj.ahora += 300
    assert c.empezar_turno() == 0        # al empezar el turno, olvida
    c.anotar("tema nuevo", "...")
    assert c.turnos() == [Turno("tema nuevo", "...")]


def test_un_turno_que_uso_la_memoria_no_la_borra_al_acabar():
    # A los 115 s se pregunta (la memoria vale y se usa); Numa habla 10 s;
    # al anotar, a los 125 s, el contexto usado debe seguir ahí.
    reloj = Reloj()
    c = Conversacion(caduca_s=120, reloj=reloj)
    c.anotar("Háblame de Roma", "Roma...")
    reloj.ahora += 115
    assert c.empezar_turno() == 1        # al empezar el turno: aún vale y se usa
    reloj.ahora += 10
    c.anotar("¿Y su primer emperador?", "Augusto.")
    assert [t.usuario for t in c.turnos()] == ["Háblame de Roma", "¿Y su primer emperador?"]
