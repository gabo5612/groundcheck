"""`groundcheck diff` — compares two runs and names what moved.

Division of labour with `gate`, on purpose:

  gate  → does this block the build?   Answers with an exit code.
  diff  → what changed and why?        Answers with concrete cases.

A gate saying "recall@5 fell 0.25" is not enough to fix anything. What's actionable is
"it fell because `alarma-e114` and `nsn-aceite-law` stopped retrieving their gold chunk".
That is why `diff` drops to case level instead of stopping at the average.
"""

from __future__ import annotations

from typing import Any

from .checks import evaluate
from .flips import Flip, classify_flips
from .metrics import RetrievedItem, mean, recall_at_k, reciprocal_rank
from .report import _response_from_json
from .schema import CATEGORIES, Suite


class DiffError(RuntimeError):
    pass


def _checks_per_case(run: dict[str, Any], suite: Suite) -> dict[str, dict[str, bool | None]]:
    cases = {c.id: c for c in suite.cases}
    out: dict[str, dict[str, bool | None]] = {}
    for obs in run["observations"]:
        case = cases.get(obs["case_id"])
        if case is None:
            continue
        results = evaluate(case, _response_from_json(obs.get("response")))
        out[obs["case_id"]] = {name: r.passed for name, r in results.items()}
    return out


def _retrieval_per_category(
    run: dict[str, Any], suite: Suite, k: int
) -> dict[str, dict[str, float | None]]:
    cases = {c.id: c for c in suite.cases}
    acc: dict[str, dict[str, list[float | None]]] = {}
    for obs in run["observations"]:
        case = cases.get(obs["case_id"])
        if case is None or case.category == "negative_control":
            continue
        resp = _response_from_json(obs.get("response"))
        items = [
            RetrievedItem.from_raw(r, i)
            for i, r in enumerate((resp.retrieved if resp else ()), start=1)
        ]
        targets = case.targets()
        row = acc.setdefault(case.category, {"recall": [], "rr": []})
        row["recall"].append(recall_at_k(items, targets, k))
        row["rr"].append(reciprocal_rank(items, targets))
    return {
        cat: {f"recall@{k}": mean(v["recall"]), "MRR": mean(v["rr"])} for cat, v in acc.items()
    }


def diff_runs(
    before: dict[str, Any], after: dict[str, Any], suite: Suite, *, k: int = 5
) -> tuple[list[Flip], dict[str, dict[str, tuple[float | None, float | None]]]]:
    """Returns `(flips, retrieval_movement_per_category)`."""
    if before["suite"]["sha256"] != after["suite"]["sha256"]:
        raise DiffError(
            "the two runs used different golden sets: the diff means nothing.\n"
            f"  before : {before['suite']['sha256'][:16]}…\n"
            f"  after  : {after['suite']['sha256'][:16]}…"
        )
    if suite.sha256 != before["suite"]["sha256"]:
        raise DiffError(
            "the suite on disk is not the one the runs used; the diff would be a lie."
        )

    flips = classify_flips(_checks_per_case(before, suite), _checks_per_case(after, suite))

    ret_before = _retrieval_per_category(before, suite, k)
    ret_after = _retrieval_per_category(after, suite, k)
    movement: dict[str, dict[str, tuple[float | None, float | None]]] = {}
    for cat in sorted(set(ret_before) | set(ret_after)):
        row = {}
        for metric in (f"recall@{k}", "MRR"):
            a = ret_before.get(cat, {}).get(metric)
            d = ret_after.get(cat, {}).get(metric)
            if a != d:
                row[metric] = (a, d)
        if row:
            movement[cat] = row
    return flips, movement


def render(
    before: dict[str, Any],
    after: dict[str, Any],
    flips: list[Flip],
    movement: dict[str, dict[str, tuple[float | None, float | None]]],
    suite: Suite,
    *,
    k: int = 5,
) -> str:
    category_of = {c.id: c.category for c in suite.cases}

    def num(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.3f}"

    def val(v: bool | None) -> str:
        return {True: "ok", False: "FAIL", None: "n/a"}[v]

    out = [""]
    out.append(f"  before   {before['system']['target']}  ·  {before['started_at']}")
    out.append(f"  after    {after['system']['target']}  ·  {after['started_at']}")
    out.append(f"  suite    {suite.name} · sha256 {suite.sha256[:16]}…")
    out.append("")

    if not flips and not movement:
        out.append("  ✓ the two runs are equivalent: no check or metric moved")
        out.append("")
        return "\n".join(out)

    if movement:
        out.append("  Retrieval that moved, by category")
        for cat, metrics in movement.items():
            for metric, (a, d) in metrics.items():
                arrow = "↓" if (a or 0) > (d or 0) else "↑"
                out.append(f"    {arrow} {cat}/{metric}: {num(a)} → {num(d)}")
        out.append("")

    # Grouping by category is the point: it names WHERE it moved, not just how much.
    by_category: dict[str, list[Flip]] = {}
    for f in flips:
        by_category.setdefault(category_of.get(f.case_id, "(no category)"), []).append(f)

    order = [c for c in CATEGORIES if c in by_category]
    order += [c for c in by_category if c not in order]

    for cat in order:
        group = by_category[cat]
        broke = sum(1 for f in group if f.kind == "broke")
        went_dark = sum(1 for f in group if f.kind == "went_dark")
        summary = []
        if broke:
            summary.append(f"{broke} broke")
        if went_dark:
            summary.append(f"{went_dark} went dark")
        tail = f"  ({', '.join(summary)})" if summary else ""
        out.append(f"  {cat}{tail}")
        for f in group:
            if f.check == "(case)":
                out.append(f"    · {f.case_id}: {f.kind}")
            else:
                out.append(
                    f"    · {f.case_id}/{f.check}: {val(f.before)} → {val(f.after)}"
                    f"   [{f.kind}]"
                )
        out.append("")

    worse = sum(1 for f in flips if f.kind in ("broke", "went_dark"))
    better = sum(1 for f in flips if f.kind in ("fixed", "lit_up"))
    out.append(f"  {len(flips)} change(s): {worse} for the worse · {better} for the better")
    out.append("  `diff` blocks nothing: that is what `groundcheck gate` is for.")
    out.append("")
    return "\n".join(out)
