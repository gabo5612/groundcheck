"""Tests del validador. Cada uno corresponde a un typo o contradiccion que, sin el
validador, apagaria un check en silencio en vez de dar error.
"""

from pathlib import Path

import pytest

from assay.suite import SuiteError, load_suite

ROOT = Path(__file__).resolve().parents[1]


def write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "s.yaml"
    p.write_text(body, "utf-8")
    return p


def test_carga_la_suite_de_humo():
    suite = load_suite(ROOT / "suites" / "mock.yaml")
    assert suite.case_count == 3
    assert suite.category_counts()["negative_control"] == 1
    assert len(suite.sha256) == 64
    caso = next(c for c in suite.cases if c.id == "torque-m24-88")
    assert caso.gold_numbers == ("680", "30")
    assert caso.forbidden_numbers == ("950", "190")
    assert caso.gold_sources[0].revision == "D"
    assert caso.gold_sources[0].pages == (147,)
    assert caso.targets() == (("LAM-2-MAINT", (147,)),)


def test_el_sha_cambia_si_cambia_un_byte(tmp_path):
    a = load_suite(write(tmp_path, "cases:\n  - id: x\n    question: q\n    category: factual_lookup\n"))
    b = load_suite(write(tmp_path, "cases:\n  - id: x\n    question: q!\n    category: factual_lookup\n"))
    assert a.sha256 != b.sha256


def test_clave_mal_escrita_es_error(tmp_path):
    # `forbiden_numbers` con una sola d: sin esta validacion, el check mas importante
    # del harness simplemente no correria y el reporte saldria verde.
    body = (
        "cases:\n  - id: x\n    question: q\n    category: factual_lookup\n"
        "    forbiden_numbers: ['950']\n"
    )
    with pytest.raises(SuiteError, match="claves desconocidas"):
        load_suite(write(tmp_path, body))


def test_categoria_invalida_es_error(tmp_path):
    body = "cases:\n  - id: x\n    question: q\n    category: factual\n"
    with pytest.raises(SuiteError, match="category` invalida"):
        load_suite(write(tmp_path, body))


def test_control_negativo_con_respuesta_de_oro_es_error(tmp_path):
    body = (
        "cases:\n  - id: x\n    question: q\n    category: negative_control\n"
        "    gold_answer: algo\n"
    )
    with pytest.raises(SuiteError, match="no puede tener `gold_answer`"):
        load_suite(write(tmp_path, body))


def test_control_negativo_que_no_debe_abstenerse_es_error(tmp_path):
    body = (
        "cases:\n  - id: x\n    question: q\n    category: negative_control\n"
        "    must_abstain: false\n"
    )
    with pytest.raises(SuiteError, match="no prueba nada"):
        load_suite(write(tmp_path, body))


def test_must_abstain_fuera_de_control_negativo_es_error(tmp_path):
    body = (
        "cases:\n  - id: x\n    question: q\n    category: factual_lookup\n"
        "    must_abstain: true\n"
    )
    with pytest.raises(SuiteError, match="categoria equivocada"):
        load_suite(write(tmp_path, body))


def test_negative_control_infiere_must_abstain(tmp_path):
    body = "cases:\n  - id: x\n    question: q\n    category: negative_control\n"
    suite = load_suite(write(tmp_path, body))
    assert suite.cases[0].must_abstain is True


def test_numero_de_oro_se_normaliza_a_string(tmp_path):
    # 680 sin comillas en YAML es int. Se compara como literal contra el texto de la
    # respuesta, asi que tiene que quedar string o la comparacion falla en silencio.
    body = (
        "cases:\n  - id: x\n    question: q\n    category: factual_lookup\n"
        "    gold_numbers: [680]\n"
    )
    suite = load_suite(write(tmp_path, body))
    assert suite.cases[0].gold_numbers == ("680",)


def test_mismo_numero_en_oro_y_prohibido_es_error(tmp_path):
    body = (
        "cases:\n  - id: x\n    question: q\n    category: factual_lookup\n"
        "    gold_numbers: ['680']\n    forbidden_numbers: ['680']\n"
    )
    with pytest.raises(SuiteError, match="a la vez"):
        load_suite(write(tmp_path, body))


def test_id_duplicado_es_error(tmp_path):
    body = (
        "cases:\n  - id: x\n    question: q\n    category: factual_lookup\n"
        "  - id: x\n    question: q2\n    category: factual_lookup\n"
    )
    with pytest.raises(SuiteError, match="id duplicado"):
        load_suite(write(tmp_path, body))


def test_gold_source_acepta_una_lista_para_multi_documento(tmp_path):
    body = (
        "cases:\n  - id: x\n    question: q\n    category: multi_documento\n"
        "    gold_source:\n"
        "      - {doc_id: WPS-014, pages: [2]}\n"
        "      - {doc_id: ITP-CLIENTE, pages: [9, 10]}\n"
    )
    suite = load_suite(write(tmp_path, body))
    assert suite.cases[0].targets() == (
        ("WPS-014", (2,)),
        ("ITP-CLIENTE", (9, 10)),
    )


def test_multi_documento_con_una_sola_fuente_es_error(tmp_path):
    # Con un solo doc_id no mide sintesis entre fuentes, que es lo unico que esa
    # categoria existe para medir.
    body = (
        "cases:\n  - id: x\n    question: q\n    category: multi_documento\n"
        "    gold_source: {doc_id: WPS-014, pages: [2]}\n"
    )
    with pytest.raises(SuiteError, match="sintesis entre fuentes"):
        load_suite(write(tmp_path, body))


def test_lista_de_gold_source_vacia_es_error(tmp_path):
    body = (
        "cases:\n  - id: x\n    question: q\n    category: factual_lookup\n"
        "    gold_source: []\n"
    )
    with pytest.raises(SuiteError, match="lista vacia"):
        load_suite(write(tmp_path, body))
