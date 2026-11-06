"""Tests de trocear: de tokens sueltos a frases para Piper."""
import pytest

from asistente.trocear import buscar_corte, trocear


def tokens(texto, tam=3):
    """Simula el streaming del LLM: el texto en trozos de `tam` caracteres."""
    return [texto[i:i + tam] for i in range(0, len(texto), tam)]


def test_corta_en_cada_fin_de_frase():
    texto = "Roma se fundó hace mucho. Tuvo reyes y emperadores. ¿Te cuento más?"
    assert list(trocear(tokens(texto))) == [
        "Roma se fundó hace mucho.", "Tuvo reyes y emperadores.", "¿Te cuento más?"]


def test_entrega_cada_frase_en_cuanto_esta_lista():
    entregadas = []
    def flujo():
        for t in tokens("Primera frase completa. Segunda frase que tarda."):
            yield t
            entregadas.append(t)
    gen = trocear(flujo())
    assert next(gen) == "Primera frase completa."
    # Se entregó a tiempo: el final de la segunda frase aún no se ha leído.
    assert "tarda" not in "".join(entregadas)


def test_frase_corta_se_junta_con_la_siguiente():
    assert list(trocear(tokens("Sí. Roma se fundó en el 753."))) == ["Sí. Roma se fundó en el 753."]


def test_no_parte_abreviatura_seguida_de_coma():
    texto = "Se fundó en el siglo IX a.C., con dos hermanos. Fin de la historia."
    assert list(trocear(tokens(texto)))[0] == "Se fundó en el siglo IX a.C., con dos hermanos."


def test_frase_larga_se_corta_en_la_coma():
    texto = ("La historia de Roma comienza en el siglo IX, con la fundación de la ciudad "
             "por los romanos, y se desarrolló a lo largo de varias centurias.")
    frases = list(trocear(tokens(texto)))
    assert len(frases) >= 2
    assert frases[0].endswith(",") and len(frases[0]) >= 12
    assert " ".join(frases) == texto  # no se pierde ni se duplica nada


def test_lo_que_sobra_sale_al_final():
    assert list(trocear(["Sin punto final"])) == ["Sin punto final"]
    assert list(trocear(["   "])) == []
    assert list(trocear([])) == []


@pytest.mark.parametrize("texto, esperado", [
    ("Hola", None),                       # sin fin de frase ni largo
    ("Hola.", None),                      # el punto aún no tiene espacio detrás
    ("Hola amigo mío. Y", 15),            # corta tras el punto
    ("Sí. Y", None),                      # demasiado corto
])
def test_buscar_corte(texto, esperado):
    assert buscar_corte(texto) == esperado
