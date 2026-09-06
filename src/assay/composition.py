"""Validation of a golden set's composition.

Composition matters more than count (§3 of the spec). A 50-question set with 2 negative
controls measures something other than what it claims to, and that **is not visible by
reading the file**: you have to count. Hence a check rather than a convention.

Provenance note: the contract was dispatched to `crew`, but the file guard aborted the run
because Claude edited `tests/test_checks.py` in parallel — the whitelist cannot tell the
worker's edits from the architect's. Lesson: do not touch the repo while crew is
dispatching. This version was written by Claude against the same tests.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CompositionIssue:
    category: str
    kind: str          # 'missing' · 'low' · 'high' · 'unknown'
    n: int
    total: int
    actual: float
    objetivo: float
    missing: int
    blocks: bool


def composition_report(
    counts: dict[str, int],
    target: dict[str, float],
    tolerance: float,
) -> list[CompositionIssue]:
    """Compare the actual composition against the target.

    Falling SHORT in a category blocks; overshooting does not. The asymmetry is deliberate:
    if `negative_control` drops below 20%, the set stops measuring hallucination and every
    number it publishes is worth less. Having extra questions in another category merely
    unbalances it.
    """
    total = sum(counts.values())
    if total == 0:
        return []

    issues: list[CompositionIssue] = []

    for category, n in counts.items():
        if category not in target:
            issues.append(
                CompositionIssue(category, "unknown", n, total, n / total, 0.0, 0, True)
            )

    for category, expected in target.items():
        n = counts.get(category, 0)
        actual = n / total
        missing = max(0, math.ceil(expected * total) - n)

        if n == 0:
            issues.append(
                CompositionIssue(category, "missing", 0, total, 0.0, expected, missing, True)
            )
        elif actual < expected - tolerance:
            issues.append(
                CompositionIssue(category, "low", n, total, actual, expected, missing, True)
            )
        elif actual > expected + tolerance:
            issues.append(
                CompositionIssue(category, "high", n, total, actual, expected, 0, False)
            )

    return sorted(issues, key=lambda i: (not i.blocks, i.category))
