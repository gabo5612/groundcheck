"""Tests de `composition_report` — gate del contrato despachado a crew.

Escritos antes de la implementacion. Un golden set con la composicion equivocada mide
otra cosa que la que dice medir, y eso no se ve leyendo el archivo.
"""

import pytest

from assay.composition import CompositionIssue, composition_report

OBJETIVO = {
    "factual_lookup": 0.30,
    "alfanumerico_exacto": 0.15,
    "procedimental": 0.15,
    "multi_documento": 0.10,
    "negative_control": 0.20,
    "revision_supersedida": 0.10,
}


def cats(**kw) -> dict[str, int]:
    base = {k: 0 for k in OBJETIVO}
    base.update(kw)
    return base


def test_una_composicion_exacta_no_tiene_problemas():
    conteo = cats(factual_lookup=15, alfanumerico_exacto=8, procedimental=7,
                  multi_documento=5, negative_control=10, revision_supersedida=5)
    assert composition_report(conteo, OBJETIVO, tolerancia=0.03) == []


def test_una_categoria_vacia_se_reporta_como_ausente():
    conteo = cats(factual_lookup=20, alfanumerico_exacto=10, procedimental=10,
                  negative_control=10)
    problemas = composition_report(conteo, OBJETIVO, tolerancia=0.03)
    ausentes = [p for p in problemas if p.kind == "ausente"]
    assert {p.category for p in ausentes} == {"multi_documento", "revision_supersedida"}
    assert all(p.blocks for p in ausentes)


def test_los_controles_negativos_por_debajo_del_objetivo_bloquean():
    """La metrica mas importante del set: si baja del 20% el set deja de medir alucinacion."""
    conteo = cats(factual_lookup=20, alfanumerico_exacto=8, procedimental=7,
                  multi_documento=5, negative_control=5, revision_supersedida=5)
    problemas = composition_report(conteo, OBJETIVO, tolerancia=0.03)
    neg = next(p for p in problemas if p.category == "negative_control")
    assert neg.kind == "bajo"
    assert neg.blocks is True
    assert neg.actual == pytest.approx(0.10)
    assert neg.objetivo == 0.20


def test_una_categoria_por_encima_del_objetivo_no_bloquea():
    conteo = cats(factual_lookup=25, alfanumerico_exacto=8, procedimental=7,
                  multi_documento=5, negative_control=10, revision_supersedida=5)
    problemas = composition_report(conteo, OBJETIVO, tolerancia=0.03)
    alto = next(p for p in problemas if p.category == "factual_lookup")
    assert alto.kind == "alto"
    assert alto.blocks is False


def test_la_tolerancia_absorbe_las_diferencias_chicas():
    # 14 de 50 = 0.28 contra un objetivo de 0.30: dentro de una tolerancia de 0.03.
    conteo = cats(factual_lookup=14, alfanumerico_exacto=9, procedimental=7,
                  multi_documento=5, negative_control=10, revision_supersedida=5)
    problemas = composition_report(conteo, OBJETIVO, tolerancia=0.03)
    assert not [p for p in problemas if p.category == "factual_lookup"]


def test_un_set_vacio_no_revienta():
    assert composition_report(cats(), OBJETIVO, tolerancia=0.03) == []


def test_una_categoria_desconocida_se_reporta():
    conteo = cats(factual_lookup=15, alfanumerico_exacto=8, procedimental=7,
                  multi_documento=5, negative_control=10, revision_supersedida=5)
    conteo["inventada"] = 3
    problemas = composition_report(conteo, OBJETIVO, tolerancia=0.03)
    desconocida = next(p for p in problemas if p.category == "inventada")
    assert desconocida.kind == "desconocida"
    assert desconocida.blocks is True


def test_el_orden_pone_primero_lo_que_bloquea():
    conteo = cats(factual_lookup=30, alfanumerico_exacto=8, procedimental=7,
                  multi_documento=0, negative_control=5, revision_supersedida=5)
    problemas = composition_report(conteo, OBJETIVO, tolerancia=0.03)
    assert problemas[0].blocks is True
    bloqueantes = [p.blocks for p in problemas]
    assert bloqueantes == sorted(bloqueantes, reverse=True)


def test_el_issue_lleva_el_conteo_y_el_faltante():
    conteo = cats(factual_lookup=15, alfanumerico_exacto=8, procedimental=7,
                  multi_documento=5, negative_control=5, revision_supersedida=5)
    problemas = composition_report(conteo, OBJETIVO, tolerancia=0.03)
    neg = next(p for p in problemas if p.category == "negative_control")
    assert neg.n == 5
    assert neg.total == 45
    # Cuantas preguntas faltan para llegar al objetivo, redondeado hacia arriba.
    assert neg.faltan == 4


def test_es_un_dataclass_comparable():
    a = CompositionIssue("x", "bajo", 5, 50, 0.10, 0.20, 5, True)
    b = CompositionIssue("x", "bajo", 5, 50, 0.10, 0.20, 5, True)
    assert a == b
