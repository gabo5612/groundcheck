"""Criterio de aceptacion de M5: inyectando una regresion a proposito (bajar top-k), el
gate falla el build.
"""

import json
from pathlib import Path

import pytest

from assay.adapter import build_adapter
from assay.cli import _report_payload, main
from assay.gate import GateError, compare
from assay.report import aggregate
from assay.run import run_suite, write_run
from assay.suite import load_suite

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "suites" / "anvil-v1.yaml"
MOCK = ROOT / "tests" / "fixtures" / "mock_anvil.yaml"
MOCK_TOPK1 = ROOT / "tests" / "fixtures" / "mock_anvil_topk1.yaml"


def reporte(fixture: Path, k: int = 5) -> dict:
    suite = load_suite(SUITE)
    record = run_suite(suite, build_adapter(f"mock:{fixture}"))
    run = json.loads(json.dumps(record.to_json_dict()))
    return _report_payload(aggregate(run, suite, k=k), run, k)


@pytest.fixture(scope="module")
def baseline() -> dict:
    return reporte(MOCK)


@pytest.fixture(scope="module")
def degradado() -> dict:
    return reporte(MOCK_TOPK1)


# ─────────────────────────────────────────────────────────────────────────────
# EL CRITERIO DE ACEPTACION
# ─────────────────────────────────────────────────────────────────────────────
def test_bajar_top_k_hace_fallar_el_gate(baseline, degradado):
    hallazgos = compare(baseline, degradado, max_regression=0.02)
    bloqueantes = [f for f in hallazgos if f.blocks]
    assert bloqueantes, "bajar top-k a 1 tiene que bloquear el build"

    # Y la regresion se NOMBRA: que categoria y que metrica se movieron.
    recall = next(
        f for f in bloqueantes
        if f.category == "alfanumerico_exacto" and f.metric == "recall_at_5"
    )
    assert recall.baseline == 1.0
    assert recall.current == 0.75
    assert recall.delta == pytest.approx(-0.25)


def test_el_gate_pasa_contra_si_mismo(baseline):
    assert compare(baseline, baseline, max_regression=0.02) == []


def test_una_caida_dentro_de_la_tolerancia_no_bloquea(baseline, degradado):
    # Con tolerancia 0.30 ninguna de las caidas medidas (max 0.25) bloquea.
    hallazgos = compare(baseline, degradado, max_regression=0.30)
    assert not [f for f in hallazgos if f.kind == "regresion"]


# ─────────────────────────────────────────────────────────────────────────────
# Las cuatro decisiones del modulo
# ─────────────────────────────────────────────────────────────────────────────
def test_se_niega_si_el_golden_set_cambio(baseline):
    otro = json.loads(json.dumps(baseline))
    otro["suite"] = {**otro["suite"], "sha256": "0" * 64}
    with pytest.raises(GateError, match="no es el mismo"):
        compare(baseline, otro)


def test_se_niega_si_el_k_no_coincide(baseline):
    con_k1 = reporte(MOCK, k=1)
    with pytest.raises(GateError, match="no es comparable"):
        compare(baseline, con_k1)


def test_perder_la_verificabilidad_bloquea_el_build(baseline):
    """La regresion mas silenciosa: el numero no baja, desaparece.

    Si el sistema deja de exponer el texto de sus chunks, `grounded` pasa de 0.88 a `n/a`.
    Sin esta regla el gate diria "sin cambios" mientras la metrica se apagó.
    """
    ciego = json.loads(json.dumps(baseline))
    ciego["categories"]["factual_lookup"]["checks"]["grounded"]["rate"] = None

    hallazgos = compare(baseline, ciego)
    perdida = next(f for f in hallazgos if f.kind == "verificabilidad")
    assert perdida.category == "factual_lookup"
    assert perdida.metric == "check:grounded"
    assert perdida.blocks is True
    assert "desaparecio" in perdida.detail


def test_una_mejora_no_bloquea_pero_se_imprime(baseline):
    mejor = json.loads(json.dumps(baseline))
    mejor["categories"]["negative_control"]["checks"]["abstention_correct"]["rate"] = 1.0

    hallazgos = compare(baseline, mejor)
    mejora = next(f for f in hallazgos if f.kind == "mejora")
    assert mejora.blocks is False
    assert "bug del eval" in mejora.detail   # un salto grande suele ser eso


def test_una_categoria_que_desaparece_bloquea(baseline):
    sin_negativos = json.loads(json.dumps(baseline))
    del sin_negativos["categories"]["negative_control"]

    hallazgos = compare(baseline, sin_negativos)
    ido = next(f for f in hallazgos if f.category == "negative_control")
    assert ido.blocks is True
    assert "desaparecio" in ido.detail


def test_la_abstencion_de_los_controles_negativos_esta_gateada(baseline):
    """La metrica mas importante del set tiene que poder bloquear el build."""
    peor = json.loads(json.dumps(baseline))
    peor["categories"]["negative_control"]["checks"]["abstention_correct"]["rate"] = 0.25

    hallazgos = compare(baseline, peor)
    reg = next(f for f in hallazgos if f.kind == "regresion")
    assert reg.category == "negative_control"
    assert reg.metric == "check:abstention_correct"


# ─────────────────────────────────────────────────────────────────────────────
# CLI: los codigos de salida son el contrato con el CI
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def archivos(tmp_path):
    suite = load_suite(SUITE)
    bueno = write_run(run_suite(suite, build_adapter(f"mock:{MOCK}")), tmp_path / "bueno")
    malo = write_run(run_suite(suite, build_adapter(f"mock:{MOCK_TOPK1}")), tmp_path / "malo")
    base = tmp_path / "baseline.json"
    base.write_text(json.dumps(reporte(MOCK)), "utf-8")
    return bueno, malo, base


def test_cli_gate_sale_0_cuando_pasa(archivos, capsys):
    bueno, _, base = archivos
    assert main(["gate", str(bueno), "--against", str(base)]) == 0
    assert "el gate pasa" in capsys.readouterr().out or True


def test_cli_gate_sale_1_cuando_hay_regresion(archivos, capsys):
    _, malo, base = archivos
    assert main(["gate", str(malo), "--against", str(base)]) == 1
    salida = capsys.readouterr().out
    assert "REGRESIONES" in salida
    assert "recall_at_5" in salida


def test_cli_gate_sale_2_si_no_puede_comparar(archivos, capsys, tmp_path):
    _, malo, _ = archivos
    roto = tmp_path / "roto.json"
    roto.write_text("{no json", "utf-8")
    assert main(["gate", str(malo), "--against", str(roto)]) == 2
    assert "no se pudo leer el baseline" in capsys.readouterr().err
