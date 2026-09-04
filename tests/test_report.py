"""Criterio de aceptacion de M4: la tabla de §5 se imprime llena con datos de una corrida
real. Y la proteccion que hace que el reporte no pueda mentir.
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
def corrida(tmp_path):
    suite = load_suite(SUITE)
    record = run_suite(suite, build_adapter(f"mock:{MOCK}"))
    path = write_run(record, tmp_path)
    return json.loads(path.read_text("utf-8")), path


def test_la_tabla_se_imprime_llena(corrida):
    run, _ = corrida
    suite = load_suite(SUITE)
    filas = aggregate(run, suite, k=5)
    salida = render(run, filas, k=5)

    # Las cuatro categorias del set v1, cada una con su n.
    for cat in ("factual_lookup", "alfanumerico_exacto", "procedimental", "negative_control"):
        assert cat in salida
    assert "TOTAL" in salida
    assert "← el que importa" in salida       # marca del control negativo, como en §5
    # Ninguna celda quedo con el guion vacio del spec: todas tienen dato o `n/a`.
    assert "—" not in salida


def test_el_reporte_dice_que_el_sistema_es_un_mock(corrida):
    """Sin esto, la tabla de una corrida guionada se captura y termina en un portfolio."""
    run, _ = corrida
    salida = render(run, aggregate(run, load_suite(SUITE)), k=5)
    assert "SISTEMA GUIONADO" in salida
    assert "NO a un RAG real" in salida


def test_las_metricas_de_retrieval_son_na_en_los_controles_negativos(corrida):
    run, _ = corrida
    filas = aggregate(run, load_suite(SUITE), k=5)
    neg = filas["negative_control"]
    # La abstencion SI se mide; recall/MRR/precision no aplican.
    assert neg.rate("abstention_correct").n_verificable == 4
    salida = render(run, filas, k=5)
    linea = next(l for l in salida.splitlines() if "negative_control" in l)
    assert linea.count("n/a") >= 3


def test_el_mock_alucina_en_dos_de_los_cuatro_controles_negativos(corrida):
    """El numero que importa del set, calculado sobre la corrida y no escrito a mano."""
    run, _ = corrida
    filas = aggregate(run, load_suite(SUITE), k=5)
    tasa = filas["negative_control"].rate("abstention_correct")
    assert (tasa.aciertos, tasa.n_verificable) == (2, 4)
    assert tasa.value == 0.5


def test_cada_celda_lleva_su_denominador(corrida):
    run, _ = corrida
    filas = aggregate(run, load_suite(SUITE), k=5)
    r = filas["factual_lookup"].rate("grounded")
    assert r.render() == f"{r.value:.2f} ({r.aciertos}/{r.n_verificable})"
    assert "/" in r.render()


# ─────────────────────────────────────────────────────────────────────────────
# La proteccion: el reporte se niega si el golden set cambio
# ─────────────────────────────────────────────────────────────────────────────
def test_el_reporte_se_niega_si_la_suite_cambio(corrida, tmp_path):
    """El fracaso silencioso que esto impide: correr el eval, ver que sale mal, ablandar
    el golden set, y reportar el mismo JSON como si nada.
    """
    run, _ = corrida
    ablandada = tmp_path / "ablandada.yaml"
    texto = SUITE.read_text("utf-8").replace(
        'forbidden_numbers: ["950", "190"]', "forbidden_numbers: []"
    )
    ablandada.write_text(texto, "utf-8")

    with pytest.raises(ReportError, match="CAMBIO desde esta corrida"):
        resolve_suite(run, suite_path=ablandada)


def test_el_reporte_avisa_si_no_encuentra_la_suite(corrida):
    run, _ = corrida
    with pytest.raises(ReportError, match="no encuentro la suite"):
        resolve_suite(run, suite_path="/no/existe.yaml")


def test_una_corrida_con_un_caso_ajeno_a_la_suite_es_error(corrida):
    run, _ = corrida
    run["observations"].append({"case_id": "inventado", "category": "factual_lookup",
                                "question": "?", "must_abstain": False, "response": None,
                                "error": None})
    with pytest.raises(ReportError, match="no esta en la suite"):
        aggregate(run, load_suite(SUITE))


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def test_cli_report_imprime_la_tabla(corrida, capsys):
    _, path = corrida
    assert main(["report", str(path)]) == 0
    salida = capsys.readouterr().out
    assert "factual_lookup" in salida and "TOTAL" in salida


def test_cli_report_json_es_json_valido(corrida, capsys):
    _, path = corrida
    assert main(["report", str(path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["k"] == 5
    neg = payload["categories"]["negative_control"]
    assert neg["n"] == 4
    assert neg["recall_at_5"] is None          # n/a se serializa como null, no como 0
    assert neg["checks"]["abstention_correct"]["rate"] == 0.5


def test_cli_report_con_k_distinto_cambia_la_precision(corrida, capsys):
    _, path = corrida
    main(["report", str(path), "--json", "--k", "1"])
    k1 = json.loads(capsys.readouterr().out)
    main(["report", str(path), "--json", "--k", "5"])
    k5 = json.loads(capsys.readouterr().out)
    # precision@k divide por k: con k mas chico, sube.
    assert k1["categories"]["factual_lookup"]["precision_at_1"] > \
        k5["categories"]["factual_lookup"]["precision_at_5"]


def test_cli_report_de_una_corrida_ilegible_sale_con_2(tmp_path, capsys):
    malo = tmp_path / "malo.json"
    malo.write_text("{no es json", "utf-8")
    assert main(["report", str(malo)]) == 2
    assert "no se pudo leer" in capsys.readouterr().err
