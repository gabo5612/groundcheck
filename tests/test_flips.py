"""Tests for `classify_flips` — the gate for the contract dispatched to crew.

These tests were written BEFORE the implementation and are the sole authority on whether
the worker's output is accepted. No model judges them.
"""

import pytest

from assay.flips import Flip, classify_flips


def test_a_check_that_breaks():
    antes = {"c1": {"grounded": True}}
    despues = {"c1": {"grounded": False}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c1", check="grounded", before=True, after=False, kind="broke")
    ]


def test_a_check_that_gets_fixed():
    antes = {"c1": {"grounded": False}}
    despues = {"c1": {"grounded": True}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c1", check="grounded", before=False, after=True, kind="fixed")
    ]


def test_losing_verifiability_is_called_went_dark():
    antes = {"c1": {"grounded": True}}
    despues = {"c1": {"grounded": None}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c1", check="grounded", before=True, after=None, kind="went_dark")
    ]


def test_becoming_verifiable_is_called_lit_up():
    antes = {"c1": {"grounded": None}}
    despues = {"c1": {"grounded": False}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c1", check="grounded", before=None, after=False, kind="lit_up")
    ]


def test_what_does_not_change_does_not_appear():
    antes = {"c1": {"grounded": True, "abstention_correct": None}}
    despues = {"c1": {"grounded": True, "abstention_correct": None}}
    assert classify_flips(antes, despues) == []


def test_a_new_case():
    antes = {}
    despues = {"c2": {"grounded": True}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c2", check="(case)", before=None, after=None, kind="new")
    ]


def test_a_disappearing_case():
    antes = {"c1": {"grounded": True}}
    despues = {}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c1", check="(case)", before=None, after=None, kind="disappeared")
    ]


def test_a_new_case_does_not_report_its_checks_one_by_one():
    """A new case is ONE finding, not six. Otherwise adding a question to the golden set
    floods the diff with noise and hides the real regressions."""
    antes = {}
    despues = {"c2": {"grounded": True, "abstention_correct": False, "revision_current": None}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c2", check="(case)", before=None, after=None, kind="new")
    ]


def test_a_new_check_on_an_existing_case_does_appear():
    antes = {"c1": {"grounded": True}}
    despues = {"c1": {"grounded": True, "revision_current": False}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c1", check="revision_current", before=None, after=False,
             kind="lit_up")
    ]


def test_a_check_disappearing_from_a_case_counts_as_went_dark():
    antes = {"c1": {"grounded": True, "revision_current": True}}
    despues = {"c1": {"grounded": True}}
    assert classify_flips(antes, despues) == [
        Flip(case_id="c1", check="revision_current", before=True, after=None,
             kind="went_dark")
    ]


def test_the_order_is_stable_and_puts_breakage_first():
    """A diff whose order changes between runs cannot be read, and what broke has to be at
    the top: it is what gets looked at first."""
    antes = {
        "z1": {"grounded": False},
        "a1": {"grounded": True, "abstention_correct": True},
    }
    despues = {
        "z1": {"grounded": True},
        "a1": {"grounded": False, "abstention_correct": None},
    }
    result = classify_flips(antes, despues)
    assert [(f.case_id, f.check, f.kind) for f in result] == [
        ("a1", "grounded", "broke"),
        ("a1", "abstention_correct", "went_dark"),
        ("z1", "grounded", "fixed"),
    ]


def test_several_cases_and_several_checks():
    antes = {
        "c1": {"grounded": True, "abstention_correct": True},
        "c2": {"grounded": None},
        "c3": {"grounded": True},
    }
    despues = {
        "c1": {"grounded": False, "abstention_correct": True},
        "c2": {"grounded": True},
        "c3": {"grounded": True},
    }
    result = classify_flips(antes, despues)
    assert len(result) == 2
    assert result[0] == Flip("c1", "grounded", True, False, "broke")
    assert result[1] == Flip("c2", "grounded", None, True, "lit_up")


def test_empty_inputs():
    assert classify_flips({}, {}) == []


def test_it_does_not_mutate_the_inputs():
    antes = {"c1": {"grounded": True}}
    despues = {"c1": {"grounded": False}}
    copia_antes = {"c1": {"grounded": True}}
    copia_despues = {"c1": {"grounded": False}}
    classify_flips(antes, despues)
    assert antes == copia_antes and despues == copia_despues


@pytest.mark.parametrize(
    "a,d,kind",
    [
        (True, False, "broke"),
        (False, True, "fixed"),
        (True, None, "went_dark"),
        (False, None, "went_dark"),
        (None, True, "lit_up"),
        (None, False, "lit_up"),
    ],
)
def test_the_six_transitions(a, d, kind):
    result = classify_flips({"c": {"x": a}}, {"c": {"x": d}})
    assert result == [Flip("c", "x", a, d, kind)]
