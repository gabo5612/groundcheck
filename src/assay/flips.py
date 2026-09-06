"""Classification of check transitions between two runs.

`gate` answers "recall@5 fell 0.25". This module answers **which cases flipped**, which is
what you need in order to fix anything: a category does not move on its own, it moves
because three concrete questions went from passing to failing.

Provenance note: this module's contract was dispatched to the local models through `crew`.
The 7B failed 3 attempts (14/20 tests) and the 14B reached 19/20, failing only the
`False -> None` transition — the classic `if not before` instead of `if before is not None`.
crew reverted the work and escalated, and this version was written by Claude. The 14B's bug
is exactly the kind a parameterised test catches and a read-through review does not.
"""

from __future__ import annotations

from dataclasses import dataclass

# Reading priority: what broke first, what is noise last.
KIND_ORDER = {
    "broke": 0,
    "went_dark": 1,
    "disappeared": 2,
    "lit_up": 3,
    "fixed": 4,
    "new": 5,
}


@dataclass(frozen=True)
class Flip:
    case_id: str
    check: str
    before: bool | None
    after: bool | None
    kind: str


def _kind(before: bool | None, after: bool | None) -> str:
    # `is None` rather than falsiness: False is a value, not an absence. Confusing them
    # makes losing the verifiability of a failing check read as an improvement.
    if before is None:
        return "lit_up"
    if after is None:
        return "went_dark"
    return "fixed" if after else "broke"


def classify_flips(
    before: dict[str, dict[str, bool | None]],
    after: dict[str, dict[str, bool | None]],
) -> list[Flip]:
    """Check transitions between two runs, ordered by severity.

    A case that appears or disappears is **one** finding, not six: otherwise adding a
    question to the golden set floods the diff and hides the real regressions.
    """
    flips: list[Flip] = []
    position: dict[tuple[str, str], int] = {}

    for case_id, checks_after in after.items():
        if case_id not in before:
            flips.append(Flip(case_id, "(case)", None, None, "new"))
            continue

        checks_before = before[case_id]
        # Reading order: the checks in `after` first, then the ones that only existed
        # before (the ones that went dark entirely).
        names = list(checks_after) + [c for c in checks_before if c not in checks_after]
        for i, name in enumerate(names):
            a = checks_before.get(name)
            d = checks_after.get(name)
            if a == d:
                continue
            position[(case_id, name)] = i
            flips.append(Flip(case_id, name, a, d, _kind(a, d)))

    for case_id in before:
        if case_id not in after:
            flips.append(Flip(case_id, "(case)", None, None, "disappeared"))

    return sorted(
        flips,
        key=lambda f: (
            KIND_ORDER[f.kind],
            f.case_id,
            position.get((f.case_id, f.check), 0),
        ),
    )
