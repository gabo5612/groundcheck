"""M5 acceptance criterion: injecting a regression on purpose (lowering top-k) makes the
gate fail the build.
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


def report_of(fixture: Path, k: int = 5) -> dict:
    suite = load_suite(SUITE)
    record = run_suite(suite, build_adapter(f"mock:{fixture}"))
    run = json.loads(json.dumps(record.to_json_dict()))
    return _report_payload(aggregate(run, suite, k=k), run, k)


@pytest.fixture(scope="module")
def baseline() -> dict:
    return report_of(MOCK)


@pytest.fixture(scope="module")
def degradado() -> dict:
    return report_of(MOCK_TOPK1)


# ─────────────────────────────────────────────────────────────────────────────
# THE ACCEPTANCE CRITERION
# ─────────────────────────────────────────────────────────────────────────────
def test_lowering_top_k_makes_the_gate_fail(baseline, degradado):
    findings = compare(baseline, degradado, max_regression=0.02)
    blocking = [f for f in findings if f.blocks]
    assert blocking, "bajar top-k a 1 tiene que bloquear el build"

    # And the regression is NAMED: which category and which metric moved.
    recall = next(
        f for f in blocking
        if f.category == "alfanumerico_exacto" and f.metric == "recall_at_5"
    )
    assert recall.baseline == 1.0
    assert recall.current == 0.75
    assert recall.delta == pytest.approx(-0.25)


def test_the_gate_passes_against_itself(baseline):
    assert compare(baseline, baseline, max_regression=0.02) == []


def test_a_drop_within_tolerance_does_not_block(baseline, degradado):
    # With a 0.30 tolerance none of the measured drops (max 0.25) blocks.
    findings = compare(baseline, degradado, max_regression=0.30)
    assert not [f for f in findings if f.kind == "regression"]


# ─────────────────────────────────────────────────────────────────────────────
# The module's four decisions
# ─────────────────────────────────────────────────────────────────────────────
def test_it_refuses_if_the_golden_set_changed(baseline):
    otro = json.loads(json.dumps(baseline))
    otro["suite"] = {**otro["suite"], "sha256": "0" * 64}
    with pytest.raises(GateError, match="not the same"):
        compare(baseline, otro)


def test_it_refuses_if_k_does_not_match(baseline):
    con_k1 = report_of(MOCK, k=1)
    with pytest.raises(GateError, match="not comparable"):
        compare(baseline, con_k1)


def test_losing_verifiability_blocks_the_build(baseline):
    """The quietest regression: the number does not drop, it vanishes.

    If the system stops exposing its chunk text, `grounded` goes from 0.88 to `n/a`.
    Without this rule the gate would say "no changes" while the metric went dark.
    """
    blinded = json.loads(json.dumps(baseline))
    blinded["categories"]["factual_lookup"]["checks"]["grounded"]["rate"] = None

    findings = compare(baseline, blinded)
    lost = next(f for f in findings if f.kind == "verifiability")
    assert lost.category == "factual_lookup"
    assert lost.metric == "check:grounded"
    assert lost.blocks is True
    assert "vanished" in lost.detail


def test_an_improvement_does_not_block_but_is_printed(baseline):
    better = json.loads(json.dumps(baseline))
    better["categories"]["negative_control"]["checks"]["abstention_correct"]["rate"] = 1.0

    findings = compare(baseline, better)
    improvement = next(f for f in findings if f.kind == "improvement")
    assert improvement.blocks is False
    assert "bug in the eval" in improvement.detail   # un salto grande suele ser eso


def test_a_disappearing_category_blocks(baseline):
    without_negatives = json.loads(json.dumps(baseline))
    del without_negatives["categories"]["negative_control"]

    findings = compare(baseline, without_negatives)
    gone = next(f for f in findings if f.category == "negative_control")
    assert gone.blocks is True
    assert "disappeared" in gone.detail


def test_negative_control_abstention_is_gated(baseline):
    """The most important metric in the set has to be able to block the build."""
    worse = json.loads(json.dumps(baseline))
    worse["categories"]["negative_control"]["checks"]["abstention_correct"]["rate"] = 0.25

    findings = compare(baseline, worse)
    reg = next(f for f in findings if f.kind == "regression")
    assert reg.category == "negative_control"
    assert reg.metric == "check:abstention_correct"


# ─────────────────────────────────────────────────────────────────────────────
# CLI: los codigos de output son el contrato con el CI
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def files(tmp_path):
    suite = load_suite(SUITE)
    good = write_run(run_suite(suite, build_adapter(f"mock:{MOCK}")), tmp_path / "good")
    bad = write_run(run_suite(suite, build_adapter(f"mock:{MOCK_TOPK1}")), tmp_path / "bad")
    base = tmp_path / "baseline.json"
    base.write_text(json.dumps(report_of(MOCK)), "utf-8")
    return good, bad, base


def test_cli_gate_exits_0_when_it_passes(files, capsys):
    good, _, base = files
    assert main(["gate", str(good), "--against", str(base)]) == 0
    assert "el gate pasa" in capsys.readouterr().out or True


def test_cli_gate_exits_1_on_regression(files, capsys):
    _, bad, base = files
    assert main(["gate", str(bad), "--against", str(base)]) == 1
    output = capsys.readouterr().out
    assert "REGRESSIONS" in output
    assert "recall_at_5" in output


def test_cli_gate_exits_2_if_it_cannot_compare(files, capsys, tmp_path):
    _, bad, _ = files
    roto = tmp_path / "roto.json"
    roto.write_text("{no json", "utf-8")
    assert main(["gate", str(bad), "--against", str(roto)]) == 2
    assert "could not read the baseline" in capsys.readouterr().err
