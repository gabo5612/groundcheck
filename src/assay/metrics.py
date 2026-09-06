"""Retrieval metrics. Set operations, with no model in the loop.

Three decisions are written out explicitly here because they are exactly the ones that,
taken silently, make two runs stop being comparable without anyone noticing:

1. **`precision_at_k` divides by `k`, not by the number retrieved.** That is the standard
   IR definition. A system returning 3 chunks with k=5 takes a real penalty, and rightly
   so: it asked for less context than was available. The retrieved count is recorded
   separately so anyone can recompute under the other convention.
2. **`recall_at_k` counts targets covered, not relevant items.** With two gold pages and
   both in the top-k it is 1.0; with only one, 0.5. Counting relevant items would give 1.0
   in the second case too if the same chunk appeared twice — and that is the classic bug
   that inflates the number.
3. **Negative controls have no retrieval metrics: they return `None`.** Not zero. A zero
   gets averaged in and drags the mean down with a data point that does not exist; `None`
   forces the report to say `n/a`, which is the truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class RetrievedItem:
    """A retrieved chunk. `rank` is 1-based: `rank=1` is the first."""

    rank: int
    doc_id: str | None = None
    page: int | None = None
    chunk_id: str | None = None
    revision: str | None = None

    @staticmethod
    def from_raw(raw: Any, rank: int) -> "RetrievedItem":
        if not isinstance(raw, dict):
            return RetrievedItem(rank=rank, chunk_id=str(raw))
        page = raw.get("page")
        if isinstance(page, bool) or not isinstance(page, int):
            page = None
        return RetrievedItem(
            rank=rank,
            doc_id=None if raw.get("doc_id") is None else str(raw["doc_id"]),
            page=page,
            chunk_id=None if raw.get("chunk_id") is None else str(raw["chunk_id"]),
            revision=None if raw.get("revision") is None else str(raw["revision"]),
        )


def matches(item: RetrievedItem, doc_id: str, pages: Sequence[int]) -> bool:
    """Does a retrieved item cover a gold target?

    If the target specifies pages and the item reports none, it **does not count**. A
    system that will not say which page it found something on cannot claim page-level
    recall: that would credit it for information it never handed over.
    """
    if item.doc_id is None or item.doc_id != doc_id:
        return False
    if not pages:
        return True
    return item.page is not None and item.page in pages


def relevance_vector(
    retrieved: Sequence[RetrievedItem], targets: Sequence[tuple[str, Sequence[int]]]
) -> list[bool]:
    """For each item in rank order: does it cover any target?"""
    return [any(matches(item, doc, pages) for doc, pages in targets) for item in retrieved]


def recall_at_k(
    retrieved: Sequence[RetrievedItem],
    targets: Sequence[tuple[str, Sequence[int]]],
    k: int,
) -> float | None:
    """Fraction of gold targets covered by the top-k. `None` when there are no targets."""
    if k <= 0:
        raise ValueError("k must be >= 1")
    if not targets:
        return None
    top = retrieved[:k]
    covered = sum(1 for doc, pages in targets if any(matches(i, doc, pages) for i in top))
    return covered / len(targets)


def precision_at_k(
    retrieved: Sequence[RetrievedItem],
    targets: Sequence[tuple[str, Sequence[int]]],
    k: int,
) -> float | None:
    """Fraction of the top-k that is relevant. Divides by `k` (see decision 1 above)."""
    if k <= 0:
        raise ValueError("k must be >= 1")
    if not targets:
        return None
    relevant = sum(relevance_vector(retrieved[:k], targets))
    return relevant / k


def reciprocal_rank(
    retrieved: Sequence[RetrievedItem], targets: Sequence[tuple[str, Sequence[int]]]
) -> float | None:
    """1 / position of the first relevant item. `0.0` when none is relevant."""
    if not targets:
        return None
    for pos, relevant in enumerate(relevance_vector(retrieved, targets), start=1):
        if relevant:
            return 1.0 / pos
    return 0.0


def mean(values: Iterable[float | None]) -> float | None:
    """Average that **ignores** `None` rather than treating it as zero.

    The corollary of decision 3: if 4 of 20 cases are negative controls, mean recall is
    computed over 16, not over 20.
    """
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def mrr(retrieved_per_case, targets_per_case) -> float | None:
    """Mean Reciprocal Rank across several cases."""
    return mean(
        reciprocal_rank(r, t) for r, t in zip(retrieved_per_case, targets_per_case, strict=True)
    )
