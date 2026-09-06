"""M4 acceptance criterion: the §5 table prints fully populated with data from a real run.
Plus the protection that stops the report from lying.
"""

import json
from pathlib import Path

import pytest

from assay.adapter import build_adapter
from assay.cli import main
from assay.report import ReportError, aggregate, render, resolve_suite
from assay.run import run_suite, write_run
from assay.suite import load_suite

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "suites" / "anvil-v1.yaml"
MOCK = ROOT / "tests" / "fixtures" / "mock_anvil.yaml"


@pytest.fixture
def run_of(tmp_path):
    suite = load_suite(SUITE)
    record = run_suite(suite, build_adapter(f"mock:{MOCK}"))
    path = write_run(record, tmp_path)
    return json.loads(path.read_text("utf-8")), path


def test_the_table_prints_fully_populated(run_of):
    run, _ = run_of
    suite = load_suite(SUITE)
    rows = aggregate(run, suite, k=5)
    output = render(run, rows, k=5)

    # The four categories of the v1 set, each with its n.
    for cat in ("factual_lookup", "alfanumerico_exacto", "procedimental", "negative_control"):
        assert cat in output
    assert "TOTAL" in output
    assert "← the one that matters" in output       # marca del control negativo, como en §5
    # No cell kept the spec's empty dash: every one has data or `n/a`.
    assert "—" not in output


def test_the_report_says_the_system_is_a_mock(run_of):
    """Without this, the table from a scripted run gets screenshotted into a portfolio."""
    run, _ = run_of
    output = render(run, aggregate(run, load_suite(SUITE)), k=5)
    assert "SCRIPTED SYSTEM" in output
    assert "NOT a real RAG" in output


def test_retrieval_metrics_are_na_on_negative_controls(run_of):
    run, _ = run_of
    rows = aggregate(run, load_suite(SUITE), k=5)
    neg = rows["negative_control"]
    # Abstention IS measured; recall/MRR/precision do not apply.
    assert neg.rate("abstention_correct").n_verifiable == 4
    output = render(run, rows, k=5)
    linea = next(l for l in output.splitlines() if "negative_control" in l)
    assert linea.count("n/a") >= 3


def test_the_mock_hallucinates_on_two_of_four_negative_controls(run_of):
    """The number that matters in the set, computed over the run and not hand-written."""
    run, _ = run_of
    rows = aggregate(run, load_suite(SUITE), k=5)
    tasa = rows["negative_control"].rate("abstention_correct")
    assert (tasa.hits, tasa.n_verifiable) == (2, 4)
    assert tasa.value == 0.5


def test_every_cell_carries_its_denominator(run_of):
    run, _ = run_of
    rows = aggregate(run, load_suite(SUITE), k=5)
    r = rows["factual_lookup"].rate("grounded")
    assert r.render() == f"{r.value:.2f} ({r.hits}/{r.n_verifiable})"
    assert "/" in r.render()


# ─────────────────────────────────────────────────────────────────────────────
# The protection: the report refuses if the golden set changed
# ─────────────────────────────────────────────────────────────────────────────
def test_the_report_refuses_if_the_suite_changed(run_of, tmp_path):
    """The silent failure this prevents: run the eval, see it go badly, soften the golden
    set, and report the same JSON as if nothing happened.
    """
    run, _ = run_of
    ablandada = tmp_path / "ablandada.yaml"
    texto = SUITE.read_text("utf-8").replace(
        'forbidden_numbers: ["950", "190"]', "forbidden_numbers: []"
    )
    ablandada.write_text(texto, "utf-8")

    with pytest.raises(ReportError, match="CHANGED since this run"):
        resolve_suite(run, suite_path=ablandada)


def test_the_report_warns_if_it_cannot_find_the_suite(run_of):
    run, _ = run_of
    with pytest.raises(ReportError, match="cannot find the suite"):
        resolve_suite(run, suite_path="/no/existe.yaml")


def test_a_run_with_a_case_foreign_to_the_suite_is_an_error(run_of):
    run, _ = run_of
    run["observations"].append({"case_id": "inventado", "category": "factual_lookup",
                                "question": "?", "must_abstain": False, "response": None,
                                "error": None})
    with pytest.raises(ReportError, match="not in the suite"):
        aggregate(run, load_suite(SUITE))


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def test_cli_report_prints_the_table(run_of, capsys):
    _, path = run_of
    assert main(["report", str(path)]) == 0
    output = capsys.readouterr().out
    assert "factual_lookup" in output and "TOTAL" in output


def test_cli_report_json_is_valid_json(run_of, capsys):
    _, path = run_of
    assert main(["report", str(path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["k"] == 5
    neg = payload["categories"]["negative_control"]
    assert neg["n"] == 4
    assert neg["recall_at_5"] is None          # n/a serialises as null, not as 0
    assert neg["checks"]["abstention_correct"]["rate"] == 0.5


def test_cli_report_with_a_different_k_changes_precision(run_of, capsys):
    _, path = run_of
    main(["report", str(path), "--json", "--k", "1"])
    k1 = json.loads(capsys.readouterr().out)
    main(["report", str(path), "--json", "--k", "5"])
    k5 = json.loads(capsys.readouterr().out)
    # precision@k divides by k: with a smaller k it goes up.
    assert k1["categories"]["factual_lookup"]["precision_at_1"] > \
        k5["categories"]["factual_lookup"]["precision_at_5"]


def test_cli_report_of_an_unreadable_run_exits_with_2(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{no es json", "utf-8")
    assert main(["report", str(bad)]) == 2
    assert "could not read" in capsys.readouterr().err
