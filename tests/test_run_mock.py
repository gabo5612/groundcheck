"""M0 acceptance criterion: `groundcheck run` runs against a mock system and emits JSON."""

import json
from pathlib import Path

from groundcheck.adapter import build_adapter
from groundcheck.cli import main
from groundcheck.run import run_suite
from groundcheck.suite import load_suite

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "suites" / "mock.yaml"
MOCK = ROOT / "tests" / "fixtures" / "mock_responses.yaml"


def test_a_run_against_the_mock_records_all_three_observations():
    suite = load_suite(SUITE)
    record = run_suite(suite, build_adapter(f"mock:{MOCK}"))

    assert len(record.observations) == 3
    assert all(o.error is None for o in record.observations)
    assert record.suite["sha256"] == suite.sha256
    assert record.system == {"kind": "mock", "target": str(MOCK)}
    assert record.finished_at is not None


def test_the_mock_script_arrives_verbatim():
    suite = load_suite(SUITE)
    record = run_suite(suite, build_adapter(f"mock:{MOCK}"))
    por_id = {o.case_id: o for o in record.observations}

    assert "680" in por_id["torque-m24-88"].response.answer
    # The deliberately scripted failure: it answers 950, which is in forbidden_numbers.
    assert "950" in por_id["alarma-e114"].response.answer
    # The negative control abstained.
    assert por_id["torque-m30-ausente"].response.abstained is True
    assert por_id["torque-m30-ausente"].response.answer is None


def test_a_run_emits_no_metric_at_all():
    """The §8 rule from the master spec, as a test — invariant, not just for M0.

    A run stores observations; metrics are derived in the report (M4). If someone adds a
    "provisional" average to `run`'s output, this breaks. A filler zero or 0.5 in an
    evaluation JSON is worse than an empty cell: it gets copied into a README and stops
    being provisional.

    Note: the `notes` field is excluded below because it is prose explaining that a run
    emits no metrics — and that sentence naturally contains the forbidden words. The guard
    aims at the DATA, not at the wording of a comment.
    """
    suite = load_suite(SUITE)
    record = run_suite(suite, build_adapter(f"mock:{MOCK}"))
    payload = record.to_json_dict()
    # `notes` is prose explaining that there are no metrics; excluding it keeps the guard
    # aimed at the DATA rather than at the wording of a comment.
    payload.pop("notes", None)
    blob = json.dumps(payload)

    for forbidden in ("recall", "mrr", "precision", "grounded", "score", "accuracy", "metric"):
        assert forbidden not in blob.lower(), f"a run must not emit `{forbidden}`"


def test_cli_run_writes_valid_json(tmp_path, capsys):
    code = main(["run", "--suite", str(SUITE), "--system", f"mock:{MOCK}", "--quiet"])
    assert code == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "M4"     # el hito del harness, no del formato
    assert payload["suite"]["case_count"] == 3
    assert payload["suite"]["category_counts"]["negative_control"] == 1
    assert len(payload["observations"]) == 3
    assert payload["notes"], "la run_of tiene que decir por que no trae metricas"


def test_cli_run_with_out_leaves_the_file(tmp_path):
    code = main(
        ["run", "--suite", str(SUITE), "--system", f"mock:{MOCK}", "--out", str(tmp_path), "--quiet"]
    )
    assert code == 0
    escritos = list(tmp_path.glob("*.json"))
    assert len(escritos) == 1
    assert json.loads(escritos[0].read_text("utf-8"))["groundcheck_version"]


def test_an_invalid_suite_exits_with_code_2(tmp_path, capsys):
    mala = tmp_path / "mala.yaml"
    mala.write_text("cases:\n  - id: x\n    question: q\n    category: inventada\n", "utf-8")
    assert main(["run", "--suite", str(mala), "--system", f"mock:{MOCK}", "--quiet"]) == 2
    assert "invalid suite" in capsys.readouterr().err


def test_pending_subcommands_do_not_pretend_to_exist(capsys):
    """None remain: `run`, `report`, `gate` and `diff` all exist as of M6.

    The test stays — if a future subcommand is ever declared in `--help`, it has to exit
    with code 2 rather than pretend to work.
    """
    from groundcheck.cli import PENDING

    for name in PENDING:
        assert main([name]) == 2
        assert "does not exist yet" in capsys.readouterr().err


def test_what_was_retrieved_reaches_the_observation():
    """`retrieved` is what makes recall@k, MRR and precision@k measurable (M1).

    The `alarma-e114` case is the one that matters: it retrieved the correct chunk at rank
    1 and still answered wrong. Without `retrieved` in the contract that case would be
    diagnosed as a search failure when it is a generation failure.
    """
    suite = load_suite(SUITE)
    record = run_suite(suite, build_adapter(f"mock:{MOCK}"))
    por_id = {o.case_id: o for o in record.observations}

    assert len(por_id["torque-m24-88"].response.retrieved) == 3
    assert por_id["torque-m24-88"].response.retrieved[2]["page"] == 147

    recuperado = por_id["alarma-e114"].response.retrieved
    assert len(recuperado) == 1 and recuperado[0]["doc_id"] == "LAM-2-ALARMS"


def test_metrics_computed_from_a_real_run():
    """Bridge M0 -> M1: metrics are derived from a run, not stored inside it."""
    from groundcheck.metrics import RetrievedItem, precision_at_k, recall_at_k, reciprocal_rank

    suite = load_suite(SUITE)
    record = run_suite(suite, build_adapter(f"mock:{MOCK}"))
    por_id = {o.case_id: o for o in record.observations}
    caso = next(c for c in suite.cases if c.id == "torque-m24-88")

    items = [
        RetrievedItem.from_raw(r, i)
        for i, r in enumerate(por_id["torque-m24-88"].response.retrieved, start=1)
    ]
    objetivos = caso.targets()

    # The gold chunk is at rank 3, computed by hand from the mock's script.
    assert recall_at_k(items, objetivos, 1) == 0.0
    assert recall_at_k(items, objetivos, 3) == 1.0
    assert precision_at_k(items, objetivos, 3) == 1 / 3
    assert reciprocal_rank(items, objetivos) == 1 / 3


def test_checks_over_a_real_mock_run():
    """M2 end to end: the mock's script produces a genuine `grounded: false`.

    `alarma-e114` answers "a torque of 950 N·m" while citing a chunk about temperature that
    mentions no 950 at all. It is an invented number, and it comes from a real CLI run, not
    from an object assembled inside the test.
    """
    from groundcheck.checks import evaluate

    suite = load_suite(SUITE)
    record = run_suite(suite, build_adapter(f"mock:{MOCK}"))
    casos = {c.id: c for c in suite.cases}
    por_id = {o.case_id: o for o in record.observations}

    bien = evaluate(casos["torque-m24-88"], por_id["torque-m24-88"].response)
    assert bien["grounded"].passed is True
    assert bien["gold_numbers_present"].passed is True
    assert bien["forbidden_numbers_absent"].passed is True
    assert bien["citation_hits_gold"].passed is True

    mal = evaluate(casos["alarma-e114"], por_id["alarma-e114"].response)
    assert mal["grounded"].passed is False
    assert "950" in mal["grounded"].evidence["unsupported"]

    negativo = evaluate(casos["torque-m30-ausente"], por_id["torque-m30-ausente"].response)
    assert negativo["abstention_correct"].passed is True
    assert negativo["grounded"].passed is None      # se abstuvo: nada que fundamentar
