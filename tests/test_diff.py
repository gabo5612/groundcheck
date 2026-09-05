"""Criterio de aceptacion de M6: compara dos corridas y nombra que categoria se movio."""

import copy
import json
from pathlib import Path

import pytest

from assay.adapter import build_adapter
from assay.cli import main
from assay.diff import DiffError, diff_runs
from assay.diff import render as render_diff
from assay.run import run_suite, write_run
from assay.suite import load_suite

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "suites" / "anvil-v1.yaml"
MOCK = ROOT / "tests" / "fixtures" / "mock_anvil.yaml"
MOCK_TOPK1 = ROOT / "tests" / "fixtures" / "mock_anvil_topk1.yaml"


def corrida(fixture: Path) -> dict:
    suite = load_suite(SUITE)
    return json.loads(json.dumps(run_suite(suite, build_adapter(f"mock:{fixture}")).to_json_dict()))


@pytest.fixture(scope="module")
def suite():
    return load_suite(SUITE)


@pytest.fixture(scope="module")
def base():
    return corrida(MOCK)


@pytest.fixture(scope="module")
def degradada():
    return corrida(MOCK_TOPK1)


# ─────────────────────────────────────────────────────────────────────────────
# EL CRITERIO: nombrar la categoria que se movio
# ─────────────────────────────────────────────────────────────────────────────
def test_nombra_la_categoria_que_se_movio(base, degradada, suite):
    _, movimiento = diff_runs(base, degradada, suite, k=5)
    assert "alfanumerico_exacto" in movimiento
    antes, despues = movimiento["alfanumerico_exacto"]["recall@5"]
    assert (antes, despues) == (1.0, 0.75)


def test_la_salida_muestra_la_flecha_y_los_dos_valores(base, degradada, suite):
    flips, movimiento = diff_runs(base, degradada, suite, k=5)
    salida = render_diff(base, degradada, flips, movimiento, suite, k=5)
    assert "↓ alfanumerico_exacto/recall@5: 1.000 → 0.750" in salida
    assert "no bloquea nada" in salida       # la division de trabajo con `gate`


def test_una_corrida_contra_si_misma_no_mueve_nada(base, suite):
    flips, movimiento = diff_runs(base, base, suite, k=5)
    assert flips == [] and movimiento == {}
    salida = render_diff(base, base, flips, movimiento, suite, k=5)
    assert "equivalentes" in salida


# ─────────────────────────────────────────────────────────────────────────────
# Flips a nivel de caso — lo que `gate` no puede decir
# ─────────────────────────────────────────────────────────────────────────────
def test_perder_el_texto_de_los_chunks_apaga_grounded_caso_por_caso(base, suite):
    """La degradacion silenciosa: el sistema deja de exponer el texto de sus chunks.

    Las respuestas y las citas siguen igual, asi que ninguna metrica de retrieval se
    mueve — y sin embargo `grounded` dejo de ser verificable en cada caso. `diff` lo
    nombra caso por caso; un promedio no lo veria.
    """
    ciega = copy.deepcopy(base)
    for obs in ciega["observations"]:
        for cita in (obs.get("response") or {}).get("citations") or []:
            cita.pop("text", None)

    flips, movimiento = diff_runs(base, ciega, suite, k=5)
    assert movimiento == {}, "el retrieval no cambio: el cambio es de verificabilidad"

    apagados = [f for f in flips if f.kind == "se_apago" and f.check == "grounded"]
    assert len(apagados) >= 8
    assert all(f.antes is not None and f.despues is None for f in apagados)

    salida = render_diff(base, ciega, flips, movimiento, suite, k=5)
    assert "se apago" in salida
    assert "ok → n/a" in salida


def test_los_flips_se_agrupan_por_categoria(base, suite):
    peor = copy.deepcopy(base)
    for obs in peor["observations"]:
        if obs["case_id"] == "alarma-e114":
            obs["response"]["answer"] = "La alarma E-114 corresponde a 9999 grados."

    flips, movimiento = diff_runs(base, peor, suite, k=5)
    salida = render_diff(base, peor, flips, movimiento, suite, k=5)
    assert "alfanumerico_exacto" in salida
    assert "alarma-e114/grounded: ok → FALLA" in salida
    assert "1 rompio" in salida


def test_un_caso_que_desaparece_se_nombra_una_vez(base, suite):
    recortada = copy.deepcopy(base)
    recortada["observations"] = [
        o for o in recortada["observations"] if o["case_id"] != "torque-m16-tapa"
    ]
    flips, _ = diff_runs(base, recortada, suite, k=5)
    idos = [f for f in flips if f.kind == "desaparecido"]
    assert len(idos) == 1 and idos[0].case_id == "torque-m16-tapa"


# ─────────────────────────────────────────────────────────────────────────────
# Se niega a mentir
# ─────────────────────────────────────────────────────────────────────────────
def test_se_niega_si_las_corridas_usaron_golden_sets_distintos(base, degradada, suite):
    otra = copy.deepcopy(degradada)
    otra["suite"] = {**otra["suite"], "sha256": "0" * 64}
    with pytest.raises(DiffError, match="golden sets distintos"):
        diff_runs(base, otra, suite, k=5)


# ─────────────────────────────────────────────────────────────────────────────
# El bug de nombres que encontro este hito
# ─────────────────────────────────────────────────────────────────────────────
def test_dos_corridas_en_el_mismo_segundo_no_se_pisan(tmp_path):
    """Antes se pisaban en silencio, y el diff comparaba una corrida contra si misma
    informando 'sin cambios' — la mentira mas cara que puede decir este harness."""
    suite = load_suite(SUITE)
    a = write_run(run_suite(suite, build_adapter(f"mock:{MOCK}")), tmp_path)
    b = write_run(run_suite(suite, build_adapter(f"mock:{MOCK_TOPK1}")), tmp_path)
    assert a != b
    assert len(list(tmp_path.glob("*.json"))) == 2
    assert json.loads(a.read_text())["system"]["target"] != \
        json.loads(b.read_text())["system"]["target"]


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def test_cli_diff(tmp_path, capsys):
    suite = load_suite(SUITE)
    a = write_run(run_suite(suite, build_adapter(f"mock:{MOCK}")), tmp_path)
    b = write_run(run_suite(suite, build_adapter(f"mock:{MOCK_TOPK1}")), tmp_path)
    assert main(["diff", str(a), str(b)]) == 0
    salida = capsys.readouterr().out
    assert "alfanumerico_exacto/recall@5" in salida


def test_cli_diff_con_archivo_ilegible_sale_2(tmp_path, capsys):
    malo = tmp_path / "malo.json"
    malo.write_text("{", "utf-8")
    assert main(["diff", str(malo), str(malo)]) == 2
    assert "no se pudo leer" in capsys.readouterr().err


def test_ya_no_quedan_subcomandos_pendientes(capsys):
    """M6 era el ultimo. `--help` ya no promete nada que no exista."""
    from assay.cli import PENDING

    assert PENDING == {}
