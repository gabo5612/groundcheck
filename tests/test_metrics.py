"""M1 acceptance criterion: recall@k, MRR and precision@k over a hand-built case whose
result is known in advance.

The expected values in this file are computed by hand and written as an exact fraction
next to each assert. They do not come from running the code and copying whatever it
returned — which is the most common way to write a metrics test that proves nothing.
"""

import pytest

from groundcheck.metrics import (
    RetrievedItem,
    matches,
    mean,
    mrr,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    relevance_vector,
)


def items(*specs) -> list[RetrievedItem]:
    """`items(("DOC", 147), ...)` en orden de rank, 1-based."""
    return [
        RetrievedItem(rank=i, doc_id=doc, page=page)
        for i, (doc, page) in enumerate(specs, start=1)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# CASO A — un solo objetivo de oro, el chunk correcto aparece en la posicion 3
#
#   objetivo: LAM-2-MAINT pagina 147
#
#   rank  documento          pagina   relevante?
#   ────  ─────────────────  ──────   ──────────
#     1   LAM-2-ALARMS         12        no
#     2   LAM-2-MAINT         150        no      <- doc correcto, pagina equivocada
#     3   LAM-2-MAINT         147        SI
#     4   LAM-2-MAINT         147        si      <- duplicado a proposito
#     5   OTRO                  1        no
#
#   vector de relevancia: [F, F, T, T, F]
# ─────────────────────────────────────────────────────────────────────────────
CASO_A = items(
    ("LAM-2-ALARMS", 12),
    ("LAM-2-MAINT", 150),
    ("LAM-2-MAINT", 147),
    ("LAM-2-MAINT", 147),
    ("OTRO", 1),
)
TARGET_A = [("LAM-2-MAINT", (147,))]


def test_case_A_relevance_vector():
    assert relevance_vector(CASO_A, TARGET_A) == [False, False, True, True, False]


def test_case_A_recall():
    assert recall_at_k(CASO_A, TARGET_A, 1) == 0.0          # 0 de 1 objetivo
    assert recall_at_k(CASO_A, TARGET_A, 2) == 0.0          # 0 de 1
    assert recall_at_k(CASO_A, TARGET_A, 3) == 1.0          # 1 de 1
    assert recall_at_k(CASO_A, TARGET_A, 5) == 1.0          # 1 de 1


def test_case_A_precision():
    assert precision_at_k(CASO_A, TARGET_A, 1) == 0.0       # 0/1
    assert precision_at_k(CASO_A, TARGET_A, 3) == pytest.approx(1 / 3)
    assert precision_at_k(CASO_A, TARGET_A, 4) == pytest.approx(2 / 4)
    assert precision_at_k(CASO_A, TARGET_A, 5) == pytest.approx(2 / 5)


def test_case_A_reciprocal_rank():
    # Primer relevante en la posicion 3 -> 1/3
    assert reciprocal_rank(CASO_A, TARGET_A) == pytest.approx(1 / 3)


def test_case_A_precision_divides_by_k_not_by_retrieved():
    """The module's decision 1, as a test.

    With k=10 and only 5 items retrieved, the denominator is still 10. If someone changes
    it to `min(k, len(retrieved))` the numbers from every previous run stop being
    comparable, so that change has to break a test.
    """
    assert precision_at_k(CASO_A, TARGET_A, 10) == pytest.approx(2 / 10)


# ─────────────────────────────────────────────────────────────────────────────
# CASO B — dos objetivos (multi_documento): la respuesta vive en dos fuentes
#
#   objetivos: LAM-2-MAINT p147  ·  ITP-9 p3
#
#   rank  documento      pagina   cubre
#     1   LAM-2-MAINT      147    objetivo 1
#     2   RUIDO              9    —
#     3   ITP-9              3    objetivo 2
# ─────────────────────────────────────────────────────────────────────────────
CASO_B = items(("LAM-2-MAINT", 147), ("RUIDO", 9), ("ITP-9", 3))
TARGETS_B = [("LAM-2-MAINT", (147,)), ("ITP-9", (3,))]


def test_case_B_recall_counts_covered_targets():
    assert recall_at_k(CASO_B, TARGETS_B, 1) == 0.5         # 1 de 2 objetivos
    assert recall_at_k(CASO_B, TARGETS_B, 2) == 0.5         # 1 de 2
    assert recall_at_k(CASO_B, TARGETS_B, 3) == 1.0         # 2 de 2


def test_case_B_precision_and_rr():
    assert precision_at_k(CASO_B, TARGETS_B, 3) == pytest.approx(2 / 3)
    assert reciprocal_rank(CASO_B, TARGETS_B) == 1.0        # relevante en posicion 1


def test_a_repeated_chunk_does_not_inflate_recall():
    """The module's decision 2, as a test.

    Two copies of the same chunk cover ONE target, not two. Counting relevant items instead
    of covered targets would give 1.0 here — the classic bug that inflates the number.
    """
    duplicates = items(("LAM-2-MAINT", 147), ("LAM-2-MAINT", 147))
    assert recall_at_k(duplicates, TARGETS_B, 2) == 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Matching and absence rules
# ─────────────────────────────────────────────────────────────────────────────
def test_without_a_reported_page_there_is_no_page_level_credit():
    sin_pagina = [RetrievedItem(rank=1, doc_id="LAM-2-MAINT", page=None)]
    assert matches(sin_pagina[0], "LAM-2-MAINT", (147,)) is False
    # If the target does not require a page, the same item does count.
    assert matches(sin_pagina[0], "LAM-2-MAINT", ()) is True


def test_a_target_without_pages_matches_by_document():
    assert recall_at_k(CASO_A, [("LAM-2-MAINT", ())], 2) == 1.0   # rank 2 es del doc


def test_without_targets_metrics_are_None_not_zero():
    """The module's decision 3, as a test: negative controls return `None`.

    A zero gets averaged in and drags the mean with a data point that does not exist.
    """
    assert recall_at_k(CASO_A, [], 5) is None
    assert precision_at_k(CASO_A, [], 5) is None
    assert reciprocal_rank(CASO_A, []) is None


def test_nothing_relevant_gives_rr_zero_not_None():
    # Unlike the previous case: here there WAS a target and the system did not retrieve
    # it. That is a legitimate zero and must be averaged as zero.
    assert reciprocal_rank(items(("RUIDO", 1)), TARGET_A) == 0.0
    assert recall_at_k(items(("RUIDO", 1)), TARGET_A, 5) == 0.0


def test_empty_retrieved_does_not_blow_up():
    assert recall_at_k([], TARGET_A, 5) == 0.0
    assert precision_at_k([], TARGET_A, 5) == 0.0
    assert reciprocal_rank([], TARGET_A) == 0.0


def test_an_invalid_k_is_an_error():
    for k in (0, -1):
        with pytest.raises(ValueError, match="k must be"):
            recall_at_k(CASO_A, TARGET_A, k)
        with pytest.raises(ValueError, match="k must be"):
            precision_at_k(CASO_A, TARGET_A, k)


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation
# ─────────────────────────────────────────────────────────────────────────────
def test_mean_ignores_None():
    # Three cases, one without a metric (negative control): average over 2, not 3.
    assert mean([1.0, None, 0.0]) == 0.5
    assert mean([None, None]) is None
    assert mean([]) is None


def test_mrr_over_the_two_hand_computed_cases():
    # RR of case A = 1/3 · RR of case B = 1  ->  MRR = (1/3 + 1) / 2 = 2/3
    result = mrr([CASO_A, CASO_B], [TARGET_A, TARGETS_B])
    assert result == pytest.approx((1 / 3 + 1.0) / 2)
    assert result == pytest.approx(2 / 3)


def test_mrr_excludes_negative_controls_from_the_average():
    # Three cases, the middle one is a negative control (no targets) -> average over 2.
    result = mrr([CASO_A, CASO_A, CASO_B], [TARGET_A, [], TARGETS_B])
    assert result == pytest.approx(2 / 3)


def test_mrr_requires_the_same_number_of_cases_and_targets():
    # `strict=True` in the zip: misaligning runs and targets would give a plausible MRR
    # computed over the wrong pairs, and that is worse than an error.
    with pytest.raises(ValueError):
        mrr([CASO_A, CASO_B], [TARGET_A])


def test_from_raw_builds_the_items():
    raw = [{"doc_id": "D", "page": 7, "chunk_id": "c1"}, "solo-un-id", {"page": "no-entero"}]
    built = [RetrievedItem.from_raw(r, i) for i, r in enumerate(raw, start=1)]
    assert built[0] == RetrievedItem(rank=1, doc_id="D", page=7, chunk_id="c1")
    assert built[1].chunk_id == "solo-un-id" and built[1].doc_id is None
    assert built[2].page is None       # a non-integer page is dropped, it does not break
