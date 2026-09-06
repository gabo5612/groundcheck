"""Tests for `composition_report` — the gate for the contract dispatched to crew.

Written before the implementation. A golden set with the wrong composition measures
something other than what it claims to, and that is not visible by reading the file.
"""

import pytest

from groundcheck.composition import CompositionIssue, composition_report

TARGET = {
    "factual_lookup": 0.30,
    "alfanumerico_exacto": 0.15,
    "procedimental": 0.15,
    "multi_documento": 0.10,
    "negative_control": 0.20,
    "revision_supersedida": 0.10,
}


def cats(**kw) -> dict[str, int]:
    base = {k: 0 for k in TARGET}
    base.update(kw)
    return base


def test_an_exact_composition_has_no_issues():
    counts = cats(factual_lookup=15, alfanumerico_exacto=8, procedimental=7,
                  multi_documento=5, negative_control=10, revision_supersedida=5)
    assert composition_report(counts, TARGET, tolerance=0.03) == []


def test_an_empty_category_is_reported_as_missing():
    counts = cats(factual_lookup=20, alfanumerico_exacto=10, procedimental=10,
                  negative_control=10)
    issues = composition_report(counts, TARGET, tolerance=0.03)
    absent = [p for p in issues if p.kind == "missing"]
    assert {p.category for p in absent} == {"multi_documento", "revision_supersedida"}
    assert all(p.blocks for p in absent)


def test_negative_controls_below_target_block():
    """The most important metric in the set: below 20% it stops measuring hallucination."""
    counts = cats(factual_lookup=20, alfanumerico_exacto=8, procedimental=7,
                  multi_documento=5, negative_control=5, revision_supersedida=5)
    issues = composition_report(counts, TARGET, tolerance=0.03)
    neg = next(p for p in issues if p.category == "negative_control")
    assert neg.kind == "low"
    assert neg.blocks is True
    assert neg.actual == pytest.approx(0.10)
    assert neg.objetivo == 0.20


def test_a_category_above_target_does_not_block():
    counts = cats(factual_lookup=25, alfanumerico_exacto=8, procedimental=7,
                  multi_documento=5, negative_control=10, revision_supersedida=5)
    issues = composition_report(counts, TARGET, tolerance=0.03)
    alto = next(p for p in issues if p.category == "factual_lookup")
    assert alto.kind == "high"
    assert alto.blocks is False


def test_tolerance_absorbs_small_differences():
    # 14 of 50 = 0.28 against a 0.30 target: within a 0.03 tolerance.
    counts = cats(factual_lookup=14, alfanumerico_exacto=9, procedimental=7,
                  multi_documento=5, negative_control=10, revision_supersedida=5)
    issues = composition_report(counts, TARGET, tolerance=0.03)
    assert not [p for p in issues if p.category == "factual_lookup"]


def test_an_empty_set_does_not_blow_up():
    assert composition_report(cats(), TARGET, tolerance=0.03) == []


def test_an_unknown_category_is_reported():
    counts = cats(factual_lookup=15, alfanumerico_exacto=8, procedimental=7,
                  multi_documento=5, negative_control=10, revision_supersedida=5)
    counts["inventada"] = 3
    issues = composition_report(counts, TARGET, tolerance=0.03)
    desconocida = next(p for p in issues if p.category == "inventada")
    assert desconocida.kind == "unknown"
    assert desconocida.blocks is True


def test_the_order_puts_blocking_issues_first():
    counts = cats(factual_lookup=30, alfanumerico_exacto=8, procedimental=7,
                  multi_documento=0, negative_control=5, revision_supersedida=5)
    issues = composition_report(counts, TARGET, tolerance=0.03)
    assert issues[0].blocks is True
    blocking = [p.blocks for p in issues]
    assert blocking == sorted(blocking, reverse=True)


def test_the_issue_carries_the_count_and_the_shortfall():
    counts = cats(factual_lookup=15, alfanumerico_exacto=8, procedimental=7,
                  multi_documento=5, negative_control=5, revision_supersedida=5)
    issues = composition_report(counts, TARGET, tolerance=0.03)
    neg = next(p for p in issues if p.category == "negative_control")
    assert neg.n == 5
    assert neg.total == 45
    # How many questions are missing to reach the target, rounded up.
    assert neg.missing == 4


def test_it_is_a_comparable_dataclass():
    a = CompositionIssue("x", "low", 5, 50, 0.10, 0.20, 5, True)
    b = CompositionIssue("x", "low", 5, 50, 0.10, 0.20, 5, True)
    assert a == b
