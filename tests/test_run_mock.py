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


def test_la_corrida_no_emite_ni_una_metrica():
    """La regla de §8 del contexto maestro, como test — invariante, no solo de M0.

    Una corrida guarda observaciones; las metricas se derivan en el reporte (M4). Si
    alguien agrega un promedio "provisional" a la salida de `run`, esto se cae. Un cero
    o un 0.5 de relleno en un JSON de evals es peor que una celda vacia: se copia a un
    README y deja de ser provisional.

    Nota: `metrics` como palabra tambien esta prohibida acá, y el modulo `assay.metrics`
    existe desde M1 — la prohibicion es sobre la SALIDA de una corrida, no sobre el
    codigo que calcula despues.
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
    assert payload["stage"] == "M4"     # el hito del harness, no del formato
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
    # `report` (M4) y `gate` (M5) ya existen y salieron de esta lista.
    for name in ("diff",):
        assert main([name]) == 2
        assert "todavia no existe" in capsys.readouterr().err


def test_lo_recuperado_llega_a_la_observacion():
    """`retrieved` es lo que hace medibles recall@k, MRR y precision@k (M1).

    El caso `alarma-e114` es el que importa: recuperó el chunk correcto en el rank 1 y
    aun así contestó mal. Sin `retrieved` en el contrato ese caso se diagnosticaría como
    fallo de búsqueda, cuando es fallo de generación.
    """
    suite = load_suite(SUITE)
    record = run_suite(suite, build_adapter(f"mock:{MOCK}"))
    por_id = {o.case_id: o for o in record.observations}

    assert len(por_id["torque-m24-88"].response.retrieved) == 3
    assert por_id["torque-m24-88"].response.retrieved[2]["page"] == 147

    recuperado = por_id["alarma-e114"].response.retrieved
    assert len(recuperado) == 1 and recuperado[0]["doc_id"] == "LAM-2-ALARMS"


def test_metricas_calculadas_desde_una_corrida_real():
    """Puente M0 -> M1: las métricas se derivan de una corrida, no se guardan en ella."""
    from assay.metrics import RetrievedItem, precision_at_k, recall_at_k, reciprocal_rank

    suite = load_suite(SUITE)
    record = run_suite(suite, build_adapter(f"mock:{MOCK}"))
    por_id = {o.case_id: o for o in record.observations}
    caso = next(c for c in suite.cases if c.id == "torque-m24-88")

    items = [
        RetrievedItem.from_raw(r, i)
        for i, r in enumerate(por_id["torque-m24-88"].response.retrieved, start=1)
    ]
    objetivos = caso.targets()

    # El chunk de oro está en el rank 3, calculado a mano sobre el guion del mock.
    assert recall_at_k(items, objetivos, 1) == 0.0
    assert recall_at_k(items, objetivos, 3) == 1.0
    assert precision_at_k(items, objetivos, 3) == 1 / 3
    assert reciprocal_rank(items, objetivos) == 1 / 3


def test_checks_sobre_una_corrida_real_del_mock():
    """M2 end to end: el guion del mock produce un `grounded: false` verdadero.

    `alarma-e114` contesta "un torque de 950 N·m" citando un chunk que habla de
    temperatura y no menciona ningún 950. Es un número inventado, y sale de una corrida
    real del CLI, no de un objeto armado en el test.
    """
    from assay.checks import evaluate

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
    assert "950" in mal["grounded"].evidence["sin_respaldo"]

    negativo = evaluate(casos["torque-m30-ausente"], por_id["torque-m30-ausente"].response)
    assert negativo["abstention_correct"].passed is True
    assert negativo["grounded"].passed is None      # se abstuvo: nada que fundamentar
