"""Criterio de aceptacion de M0: `assay run` corre contra un sistema mock y emite JSON."""

import json
from pathlib import Path

from assay.adapter import build_adapter
from assay.cli import main
from assay.run import run_suite
from assay.suite import load_suite

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "suites" / "mock.yaml"
MOCK = ROOT / "tests" / "fixtures" / "mock_responses.yaml"


def test_corrida_contra_mock_registra_las_tres_observaciones():
    suite = load_suite(SUITE)
    record = run_suite(suite, build_adapter(f"mock:{MOCK}"))

    assert len(record.observations) == 3
    assert all(o.error is None for o in record.observations)
    assert record.suite["sha256"] == suite.sha256
    assert record.system == {"kind": "mock", "target": str(MOCK)}
    assert record.finished_at is not None


def test_el_guion_del_mock_llega_tal_cual():
    suite = load_suite(SUITE)
    record = run_suite(suite, build_adapter(f"mock:{MOCK}"))
    por_id = {o.case_id: o for o in record.observations}

    assert "680" in por_id["torque-m24-88"].response.answer
    # El fallo guionado a proposito: contesta 950, que esta en forbidden_numbers.
    assert "950" in por_id["alarma-e114"].response.answer
    # El control negativo se abstuvo.
    assert por_id["torque-m30-ausente"].response.abstained is True
    assert por_id["torque-m30-ausente"].response.answer is None


def test_M0_no_emite_ni_una_metrica():
    """La regla de §8 del contexto maestro, como test.

    Si alguien agrega un promedio "provisional" a la salida de M0, esto se cae. Un cero
    o un 0.5 de relleno en un JSON de evals es peor que una celda vacia: se copia a un
    README y deja de ser provisional.
    """
    suite = load_suite(SUITE)
    record = run_suite(suite, build_adapter(f"mock:{MOCK}"))
    blob = json.dumps(record.to_json_dict())

    for prohibido in ("recall", "mrr", "precision", "grounded", "score", "accuracy", "metrics"):
        assert prohibido not in blob.lower(), f"M0 no deberia emitir `{prohibido}`"


def test_cli_run_escribe_json_valido(tmp_path, capsys):
    code = main(["run", "--suite", str(SUITE), "--system", f"mock:{MOCK}", "--quiet"])
    assert code == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "M0"
    assert payload["suite"]["case_count"] == 3
    assert payload["suite"]["category_counts"]["negative_control"] == 1
    assert len(payload["observations"]) == 3
    assert payload["notes"], "la corrida tiene que decir por que no trae metricas"


def test_cli_run_con_out_deja_el_archivo(tmp_path):
    code = main(
        ["run", "--suite", str(SUITE), "--system", f"mock:{MOCK}", "--out", str(tmp_path), "--quiet"]
    )
    assert code == 0
    escritos = list(tmp_path.glob("*.json"))
    assert len(escritos) == 1
    assert json.loads(escritos[0].read_text("utf-8"))["assay_version"]


def test_suite_invalida_sale_con_codigo_2(tmp_path, capsys):
    mala = tmp_path / "mala.yaml"
    mala.write_text("cases:\n  - id: x\n    question: q\n    category: inventada\n", "utf-8")
    assert main(["run", "--suite", str(mala), "--system", f"mock:{MOCK}", "--quiet"]) == 2
    assert "suite invalida" in capsys.readouterr().err


def test_subcomandos_pendientes_no_fingen_existir(capsys):
    for name in ("report", "gate", "diff"):
        assert main([name]) == 2
        assert "todavia no existe" in capsys.readouterr().err
