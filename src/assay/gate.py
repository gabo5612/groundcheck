"""CI gate: fails the build when a metric degrades.

This is the piece that turns the harness into something that *protects*, rather than a
report someone looks at when they remember to. Without a gate the real sequence is: someone
changes the chunk size, numeric accuracy drops 12%, nobody runs the eval, and the system
ends up worse with no moment at which that becomes visible.

Four decisions, each with its own test:

1. **It refuses to compare if the golden set changed.** Comparing against a baseline
   measured with a different set is not a comparison, it is a coincidence. The sha256 is
   compared.
2. **It refuses to compare if `k` differs.** recall@1 against recall@5 would produce a
   "regression" invented by the parameter, not by the system.
3. **Losing the ability to verify is a regression.** If the baseline had
   `grounded 0.90 (10/10)` and now reads `n/a` because the system stopped exposing its
   chunk text, the number did not "hold": it vanished. That fails. It is the quietest way
   for a metric to stop meaning anything.
4. **An improvement never fails the gate**, and is printed anyway: a large jump upward is
   usually a bug in the eval, not a miracle in the system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_MAX_REGRESSION = 0.02


class GateError(RuntimeError):
    pass


@dataclass(frozen=True)
class Finding:
    category: str
    metric: str
    baseline: float | None
    current: float | None
    kind: str          # "regression" · "verifiability" · "improvement" · "new"
    detail: str

    @property
    def blocks(self) -> bool:
        return self.kind in ("regression", "verifiability")

    @property
    def delta(self) -> float | None:
        if self.baseline is None or self.current is None:
            return None
        return self.current - self.baseline


def _metric_items(cat_data: dict[str, Any]) -> dict[str, float | None]:
    """Comparable metrics for one category: retrieval plus each check's rate."""
    out: dict[str, float | None] = {}
    for key, value in cat_data.items():
        if key in ("n", "errors", "checks"):
            continue
        if isinstance(value, (int, float)) or value is None:
            out[key] = value
    for name, data in (cat_data.get("checks") or {}).items():
        out[f"check:{name}"] = data.get("rate")
    return out


def compare(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    max_regression: float = DEFAULT_MAX_REGRESSION,
) -> list[Finding]:
    if baseline["suite"]["sha256"] != current["suite"]["sha256"]:
        raise GateError(
            "the golden set is not the same as the baseline's: the comparison means "
            "nothing.\n"
            f"  baseline : {baseline['suite']['sha256'][:16]}…\n"
            f"  run      : {current['suite']['sha256'][:16]}…\n"
            "If the set changed on purpose, regenerate the baseline and say so in the commit."
        )
    if baseline.get("k") != current.get("k"):
        raise GateError(
            f"the baseline was measured with k={baseline.get('k')} and this run with "
            f"k={current.get('k')}. recall@k with a different k is not comparable."
        )

    findings: list[Finding] = []
    cats_base = baseline["categories"]
    cats_cur = current["categories"]

    for cat, base_data in cats_base.items():
        cur_data = cats_cur.get(cat)
        if cur_data is None:
            findings.append(Finding(
                cat, "(category)", None, None, "verifiability",
                "the category disappeared from the run",
            ))
            continue

        base_metrics = _metric_items(base_data)
        cur_metrics = _metric_items(cur_data)

        for metric, base_val in base_metrics.items():
            cur_val = cur_metrics.get(metric)

            if base_val is None:
                if cur_val is not None:
                    findings.append(Finding(
                        cat, metric, None, cur_val, "new",
                        "it was not verifiable before and now it is",
                    ))
                continue

            if cur_val is None:
                findings.append(Finding(
                    cat, metric, base_val, None, "verifiability",
                    "stopped being verifiable — the number did not hold, it vanished",
                ))
                continue

            delta = cur_val - base_val
            if delta < -max_regression:
                findings.append(Finding(
                    cat, metric, base_val, cur_val, "regression",
                    f"fell {abs(delta):.3f}, more than the {max_regression:.3f} tolerance",
                ))
            elif delta > max_regression:
                findings.append(Finding(
                    cat, metric, base_val, cur_val, "improvement",
                    f"rose {delta:.3f} — check this is not a bug in the eval",
                ))

    for cat in cats_cur:
        if cat not in cats_base:
            findings.append(Finding(
                cat, "(category)", None, None, "new", "new category, no baseline",
            ))

    order = {"regression": 0, "verifiability": 1, "improvement": 2, "new": 3}
    return sorted(findings, key=lambda f: (order[f.kind], f.category, f.metric))


def render(findings: list[Finding], *, max_regression: float) -> str:
    out: list[str] = [""]
    blocking = [f for f in findings if f.blocks]

    def fmt(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.3f}"

    if not findings:
        out.append(f"  ✓ no changes outside the tolerance (±{max_regression:.3f})")
        out.append("")
        return "\n".join(out)

    for kind, title in (
        ("regression", "REGRESSIONS — these block the build"),
        ("verifiability", "VERIFIABILITY LOST — blocks the build"),
        ("improvement", "improvements (do not block)"),
        ("new", "new (does not block)"),
    ):
        group = [f for f in findings if f.kind == kind]
        if not group:
            continue
        out.append(f"  {title}")
        for f in group:
            out.append(
                f"    {f.category}/{f.metric}: {fmt(f.baseline)} → {fmt(f.current)}  · {f.detail}"
            )
        out.append("")

    out.append(
        f"  ✗ the gate FAILS: {len(blocking)} blocking finding(s)"
        if blocking
        else "  ✓ the gate passes: no blocking findings"
    )
    out.append("")
    return "\n".join(out)
