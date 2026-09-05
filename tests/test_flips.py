"""Tests de `classify_flips` — el gate del contrato despachado a crew.

Estos tests se escribieron ANTES de la implementacion y son la unica autoridad sobre si
el trabajo del obrero se acepta. Ningun modelo los juzga.
"""

import pytest

from assay.flips import Flip, classify_flips


def test_un_check_que_rompe():
    antes = {"c1": {"grounded": True}}
    despues = {"c1": {"grounded": False}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c1", check="grounded", antes=True, despues=False, kind="rompio")
    ]


def test_un_check_que_se_arregla():
    antes = {"c1": {"grounded": False}}
    despues = {"c1": {"grounded": True}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c1", check="grounded", antes=False, despues=True, kind="arreglo")
    ]


def test_perder_la_verificabilidad_se_llama_se_apago():
    antes = {"c1": {"grounded": True}}
    despues = {"c1": {"grounded": None}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c1", check="grounded", antes=True, despues=None, kind="se_apago")
    ]


def test_pasar_a_ser_verificable_se_llama_se_prendio():
    antes = {"c1": {"grounded": None}}
    despues = {"c1": {"grounded": False}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c1", check="grounded", antes=None, despues=False, kind="se_prendio")
    ]


def test_lo_que_no_cambia_no_aparece():
    antes = {"c1": {"grounded": True, "abstention_correct": None}}
    despues = {"c1": {"grounded": True, "abstention_correct": None}}
    assert classify_flips(antes, despues) == []


def test_un_caso_nuevo():
    antes = {}
    despues = {"c2": {"grounded": True}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c2", check="(caso)", antes=None, despues=None, kind="nuevo")
    ]


def test_un_caso_que_desaparece():
    antes = {"c1": {"grounded": True}}
    despues = {}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c1", check="(caso)", antes=None, despues=None, kind="desaparecido")
    ]


def test_un_caso_nuevo_no_reporta_sus_checks_uno_por_uno():
    """Un caso nuevo es UN hallazgo, no seis. Si no, agregar una pregunta al golden set
    inunda el diff con ruido y esconde las regresiones reales."""
    antes = {}
    despues = {"c2": {"grounded": True, "abstention_correct": False, "revision_current": None}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c2", check="(caso)", antes=None, despues=None, kind="nuevo")
    ]


def test_un_check_nuevo_en_un_caso_existente_si_aparece():
    antes = {"c1": {"grounded": True}}
    despues = {"c1": {"grounded": True, "revision_current": False}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c1", check="revision_current", antes=None, despues=False,
             kind="se_prendio")
    ]


def test_un_check_que_desaparece_del_caso_cuenta_como_apagado():
    antes = {"c1": {"grounded": True, "revision_current": True}}
    despues = {"c1": {"grounded": True}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c1", check="revision_current", antes=True, despues=None,
             kind="se_apago")
    ]


def test_el_orden_es_estable_y_pone_primero_lo_que_rompio():
    """Un diff que cambia de orden entre corridas no se puede leer, y lo que rompio tiene
    que estar arriba: es lo que se mira primero."""
    antes = {
        "z1": {"grounded": False},
        "a1": {"grounded": True, "abstention_correct": True},
    }
    despues = {
        "z1": {"grounded": True},
        "a1": {"grounded": False, "abstention_correct": None},
    }
    resultado = classify_flips(antes, despues)
    assert [(f.case_id, f.check, f.kind) for f in resultado] == [
        ("a1", "grounded", "rompio"),
        ("a1", "abstention_correct", "se_apago"),
        ("z1", "grounded", "arreglo"),
    ]


def test_varios_casos_y_varios_checks():
    antes = {
        "c1": {"grounded": True, "abstention_correct": True},
        "c2": {"grounded": None},
        "c3": {"grounded": True},
    }
    despues = {
        "c1": {"grounded": False, "abstention_correct": True},
        "c2": {"grounded": True},
        "c3": {"grounded": True},
    }
    resultado = classify_flips(antes, despues)
    assert len(resultado) == 2
    assert resultado[0] == Flip("c1", "grounded", True, False, "rompio")
    assert resultado[1] == Flip("c2", "grounded", None, True, "se_prendio")


def test_entradas_vacias():
    assert classify_flips({}, {}) == []


def test_no_muta_las_entradas():
    antes = {"c1": {"grounded": True}}
    despues = {"c1": {"grounded": False}}
    copia_antes = {"c1": {"grounded": True}}
    copia_despues = {"c1": {"grounded": False}}
    classify_flips(antes, despues)
    assert antes == copia_antes and despues == copia_despues


@pytest.mark.parametrize(
    "a,d,kind",
    [
        (True, False, "rompio"),
        (False, True, "arreglo"),
        (True, None, "se_apago"),
        (False, None, "se_apago"),
        (None, True, "se_prendio"),
        (None, False, "se_prendio"),
    ],
)
def test_las_seis_transiciones(a, d, kind):
    resultado = classify_flips({"c": {"x": a}}, {"c": {"x": d}})
    assert resultado == [Flip("c", "x", a, d, kind)]
