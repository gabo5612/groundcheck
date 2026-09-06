"""M6 acceptance criterion: compares two runs and names which category moved."""

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


def run_of(fixture: Path) -> dict:
    suite = load_suite(SUITE)
    return json.loads(json.dumps(run_suite(suite, build_adapter(f"mock:{fixture}")).to_json_dict()))


@pytest.fixture(scope="module")
def suite():
    return load_suite(SUITE)


@pytest.fixture(scope="module")
def base():
    return run_of(MOCK)


@pytest.fixture(scope="module")
def degraded():
    return run_of(MOCK_TOPK1)


# ─────────────────────────────────────────────────────────────────────────────
# EL CRITERIO: nombrar la categoria que se movio
# ─────────────────────────────────────────────────────────────────────────────
def test_it_names_the_category_that_moved(base, degraded, suite):
    _, movement = diff_runs(base, degraded, suite, k=5)
    assert "alfanumerico_exacto" in movement
    antes, despues = movement["alfanumerico_exacto"]["recall@5"]
    assert (antes, despues) == (1.0, 0.75)


def test_la_output_muestra_la_flecha_y_los_dos_valores(base, degraded, suite):
    flips, movement = diff_runs(base, degraded, suite, k=5)
    output = render_diff(base, degraded, flips, movement, suite, k=5)
    assert "↓ alfanumerico_exacto/recall@5: 1.000 → 0.750" in output
    assert "blocks nothing" in output       # la division de trabajo con `gate`


def test_a_run_against_itself_moves_nothing(base, suite):
    flips, movement = diff_runs(base, base, suite, k=5)
    assert flips == [] and movement == {}
    output = render_diff(base, base, flips, movement, suite, k=5)
    assert "equivalent" in output


# ─────────────────────────────────────────────────────────────────────────────
# Case-level flips — what `gate` cannot tell you
# ─────────────────────────────────────────────────────────────────────────────
def test_losing_chunk_text_darkens_grounded_case_by_case(base, suite):
    """The silent degradation: the system stops exposing its chunk text.

    Answers and citations stay the same, so no retrieval metric moves — and yet `grounded`
    stopped being verifiable on every case. `diff` names it case by case; an average would
    not see it.
    """
    blinded = copy.deepcopy(base)
    for obs in blinded["observations"]:
        for cita in (obs.get("response") or {}).get("citations") or []:
            cita.pop("text", None)

    flips, movement = diff_runs(base, blinded, suite, k=5)
    assert movement == {}, "el retrieval no cambio: el cambio es de verificabilidad"

    gone_dark = [f for f in flips if f.kind == "went_dark" and f.check == "grounded"]
    assert len(gone_dark) >= 8
    assert all(f.before is not None and f.after is None for f in gone_dark)

    output = render_diff(base, blinded, flips, movement, suite, k=5)
    assert "went dark" in output
    assert "ok → n/a" in output


def test_flips_are_grouped_by_category(base, suite):
    worse = copy.deepcopy(base)
    for obs in worse["observations"]:
        if obs["case_id"] == "alarma-e114":
            obs["response"]["answer"] = "La alarma E-114 corresponde a 9999 grados."

    flips, movement = diff_runs(base, worse, suite, k=5)
    output = render_diff(base, worse, flips, movement, suite, k=5)
    assert "alfanumerico_exacto" in output
    assert "alarma-e114/grounded: ok → FAIL" in output
    assert "1 broke" in output


def test_a_disappearing_case_is_named_once(base, suite):
    trimmed = copy.deepcopy(base)
    trimmed["observations"] = [
        o for o in trimmed["observations"] if o["case_id"] != "torque-m16-tapa"
    ]
    flips, _ = diff_runs(base, trimmed, suite, k=5)
    gone = [f for f in flips if f.kind == "disappeared"]
    assert len(gone) == 1 and gone[0].case_id == "torque-m16-tapa"


# ─────────────────────────────────────────────────────────────────────────────
# It refuses to lie
# ─────────────────────────────────────────────────────────────────────────────
def test_it_refuses_if_the_runs_used_different_golden_sets(base, degraded, suite):
    otra = copy.deepcopy(degraded)
    otra["suite"] = {**otra["suite"], "sha256": "0" * 64}
    with pytest.raises(DiffError, match="different golden sets"):
        diff_runs(base, otra, suite, k=5)


# ─────────────────────────────────────────────────────────────────────────────
# The filename bug this milestone found
# ─────────────────────────────────────────────────────────────────────────────
def test_two_runs_in_the_same_second_do_not_overwrite(tmp_path):
    """They used to overwrite silently, and the diff compared a run against itself
    reporting 'no changes' — the most expensive lie this harness can tell."""
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
    output = capsys.readouterr().out
    assert "alfanumerico_exacto/recall@5" in output


def test_cli_diff_with_an_unreadable_file_exits_2(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{", "utf-8")
    assert main(["diff", str(bad), str(bad)]) == 2
    assert "could not read" in capsys.readouterr().err


def test_no_pending_subcommands_remain(capsys):
    """M6 was the last one. `--help` no longer promises anything that does not exist."""
    from assay.cli import PENDING

    assert PENDING == {}
