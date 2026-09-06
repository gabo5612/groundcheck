"""Validator tests. Each one corresponds to a typo or contradiction that, without the
validator, would silently switch a check off instead of raising an error.
"""

from pathlib import Path

import pytest

from assay.suite import SuiteError, load_suite

ROOT = Path(__file__).resolve().parents[1]


def write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "s.yaml"
    p.write_text(body, "utf-8")
    return p


def test_loads_the_smoke_suite():
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


def test_the_sha_changes_when_a_byte_changes(tmp_path):
    a = load_suite(write(tmp_path, "cases:\n  - id: x\n    question: q\n    category: factual_lookup\n"))
    b = load_suite(write(tmp_path, "cases:\n  - id: x\n    question: q!\n    category: factual_lookup\n"))
    assert a.sha256 != b.sha256


def test_a_misspelled_key_is_an_error(tmp_path):
    # `forbiden_numbers` with a single d: without this validation the harness's most
    # important check simply would not run and the report would come out green.
    body = (
        "cases:\n  - id: x\n    question: q\n    category: factual_lookup\n"
        "    forbiden_numbers: ['950']\n"
    )
    with pytest.raises(SuiteError, match="unknown keys"):
        load_suite(write(tmp_path, body))


def test_an_invalid_category_is_an_error(tmp_path):
    body = "cases:\n  - id: x\n    question: q\n    category: factual\n"
    with pytest.raises(SuiteError, match="invalid `category`"):
        load_suite(write(tmp_path, body))


def test_a_negative_control_with_a_gold_answer_is_an_error(tmp_path):
    body = (
        "cases:\n  - id: x\n    question: q\n    category: negative_control\n"
        "    gold_answer: algo\n"
    )
    with pytest.raises(SuiteError, match="cannot have a `gold_answer`"):
        load_suite(write(tmp_path, body))


def test_a_negative_control_that_need_not_abstain_is_an_error(tmp_path):
    body = (
        "cases:\n  - id: x\n    question: q\n    category: negative_control\n"
        "    must_abstain: false\n"
    )
    with pytest.raises(SuiteError, match="proves nothing"):
        load_suite(write(tmp_path, body))


def test_must_abstain_outside_a_negative_control_is_an_error(tmp_path):
    body = (
        "cases:\n  - id: x\n    question: q\n    category: factual_lookup\n"
        "    must_abstain: true\n"
    )
    with pytest.raises(SuiteError, match="wrong category"):
        load_suite(write(tmp_path, body))


def test_negative_control_infers_must_abstain(tmp_path):
    body = "cases:\n  - id: x\n    question: q\n    category: negative_control\n"
    suite = load_suite(write(tmp_path, body))
    assert suite.cases[0].must_abstain is True


def test_a_gold_number_is_normalised_to_a_string(tmp_path):
    # 680 without quotes in YAML is an int. It is compared literally against the answer's
    # text, so it must end up a string or the comparison fails silently.
    body = (
        "cases:\n  - id: x\n    question: q\n    category: factual_lookup\n"
        "    gold_numbers: [680]\n"
    )
    suite = load_suite(write(tmp_path, body))
    assert suite.cases[0].gold_numbers == ("680",)


def test_the_same_number_in_gold_and_forbidden_is_an_error(tmp_path):
    body = (
        "cases:\n  - id: x\n    question: q\n    category: factual_lookup\n"
        "    gold_numbers: ['680']\n    forbidden_numbers: ['680']\n"
    )
    with pytest.raises(SuiteError, match="is in both"):
        load_suite(write(tmp_path, body))


def test_a_duplicate_id_is_an_error(tmp_path):
    body = (
        "cases:\n  - id: x\n    question: q\n    category: factual_lookup\n"
        "  - id: x\n    question: q2\n    category: factual_lookup\n"
    )
    with pytest.raises(SuiteError, match="duplicate id"):
        load_suite(write(tmp_path, body))


def test_gold_source_accepts_a_list_for_multi_document(tmp_path):
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


def test_multi_document_with_a_single_source_is_an_error(tmp_path):
    # With a single doc_id it measures no synthesis across sources, which is the only
    # thing that category exists to measure.
    body = (
        "cases:\n  - id: x\n    question: q\n    category: multi_documento\n"
        "    gold_source: {doc_id: WPS-014, pages: [2]}\n"
    )
    with pytest.raises(SuiteError, match="synthesis"):
        load_suite(write(tmp_path, body))


def test_an_empty_gold_source_list_is_an_error(tmp_path):
    body = (
        "cases:\n  - id: x\n    question: q\n    category: factual_lookup\n"
        "    gold_source: []\n"
    )
    with pytest.raises(SuiteError, match="empty list"):
        load_suite(write(tmp_path, body))
