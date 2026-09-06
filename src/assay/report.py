"""Per-category report — the harness's product.

A single global number ("78% accurate") supports no decision. What gets published is the
breakdown: how much recall on table questions, how much abstention on negative controls,
how much groundedness on alphanumeric ones. That names WHAT to fix.

Two honesty rules implemented here:

1. **The report reloads the suite and compares its sha256 against the one the run stored.**
   If they differ, it refuses to report. Without this, someone could run the eval, see it
   go badly, soften the golden set and report the same JSON as if nothing happened — which
   is exactly the silent failure this project exists to prevent.

2. **Every cell carries its denominator.** A groundedness rate of 1.00 over 2 verifiable
   cases out of 8 is not the same as over 8 of 8, and an average without n is an opinion
   with decimals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .checks import evaluate
from .metrics import RetrievedItem, mean, precision_at_k, recall_at_k, reciprocal_rank
from .schema import CATEGORIES, Case, Response, Suite
from .suite import load_suite

CHECK_COLUMNS = ("grounded", "gold_numbers_present", "forbidden_numbers_absent",
                 "forbidden_codes_absent", "citation_hits_gold", "abstention_correct",
                 "revision_current")


class ReportError(RuntimeError):
    pass


@dataclass
class Rate:
    """A rate with its denominator. `n_verifiable` can be 0: then there is no rate."""

    hits: int = 0
    n_verifiable: int = 0
    n_total: int = 0

    @property
    def value(self) -> float | None:
        return None if self.n_verifiable == 0 else self.hits / self.n_verifiable

    def render(self) -> str:
        if self.n_verifiable == 0:
            return "n/a"
        return f"{self.value:.2f} ({self.hits}/{self.n_verifiable})"


@dataclass
class CategoryRow:
    category: str
    n: int = 0
    recall: list[float | None] = field(default_factory=list)
    precision: list[float | None] = field(default_factory=list)
    rr: list[float | None] = field(default_factory=list)
    checks: dict[str, Rate] = field(default_factory=dict)
    errors: int = 0

    def rate(self, name: str) -> Rate:
        return self.checks.setdefault(name, Rate())


def _response_from_json(raw: dict[str, Any] | None) -> Response | None:
    if raw is None:
        return None
    return Response(
        answer=raw.get("answer"),
        citations=tuple(raw.get("citations") or ()),
        retrieved=tuple(raw.get("retrieved") or ()),
        abstained=bool(raw.get("abstained")),
        latency_ms=raw.get("latency_ms"),
        extra=tuple((k, v) for k, v in (raw.get("extra") or [])),
    )


def load_run(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text("utf-8"))


def resolve_suite(run: dict[str, Any], *, suite_path: str | Path | None = None) -> Suite:
    """Loads the run's suite and **verifies its sha256**."""
    declared = run["suite"]["sha256"]
    path = Path(suite_path or run["suite"]["path"])
    if not path.exists():
        raise ReportError(
            f"cannot find the suite {path} the run used. Pass it with --suite if it moved."
        )
    suite = load_suite(path)
    if suite.sha256 != declared:
        raise ReportError(
            "the golden set CHANGED since this run and the report would be a lie.\n"
            f"  run  : {declared[:16]}…\n"
            f"  file : {suite.sha256[:16]}…\n"
            "Re-run `assay run` with the current set, or report against the set's commit."
        )
    return suite


def aggregate(run: dict[str, Any], suite: Suite, *, k: int = 5) -> dict[str, CategoryRow]:
    cases: dict[str, Case] = {c.id: c for c in suite.cases}
    rows: dict[str, CategoryRow] = {}

    for obs in run["observations"]:
        case = cases.get(obs["case_id"])
        if case is None:
            raise ReportError(f"the run carries a case {obs['case_id']!r} that is not in the suite")
        row = rows.setdefault(case.category, CategoryRow(category=case.category))
        row.n += 1

        if obs.get("error"):
            row.errors += 1
            continue

        response = _response_from_json(obs.get("response"))
        targets = case.targets()
        items = [
            RetrievedItem.from_raw(r, i)
            for i, r in enumerate((response.retrieved if response else ()), start=1)
        ]
        row.recall.append(recall_at_k(items, targets, k))
        row.precision.append(precision_at_k(items, targets, k))
        row.rr.append(reciprocal_rank(items, targets))

        for name, res in evaluate(case, response).items():
            r = row.rate(name)
            r.n_total += 1
            if res.passed is not None:
                r.n_verifiable += 1
                r.hits += int(res.passed)

    return rows


def _cell(value: float | None, samples: list[float | None]) -> str:
    if value is None:
        return "n/a"
    n = sum(1 for v in samples if v is not None)
    return f"{value:.2f} ({n})"


def render(run: dict[str, Any], rows: dict[str, CategoryRow], *, k: int = 5) -> str:
    system = run["system"]
    out: list[str] = []

    out.append("")
    out.append(f"  suite      {run['suite']['name']}  ·  sha256 {run['suite']['sha256'][:16]}…")
    out.append(f"  system     {system['kind']}  ·  {system['target']}")
    out.append(f"  run        {run['started_at']}  ·  assay {run['assay_version']} ({run['stage']})")
    if system["kind"] == "mock":
        # Without this, the table from a run against a mock gets screenshotted and ends up
        # in a portfolio as if it were a measurement of the real system.
        out.append("")
        out.append("  ⚠️  SCRIPTED SYSTEM (mock): these numbers measure the mock, NOT a real RAG.")
    out.append("")

    header = f"  {'category':<24}{'n':>4}  {f'recall@{k}':>12}{'MRR':>12}{f'prec@{k}':>12}" \
             f"{'grounded':>14}{'abstention':>14}"
    out.append(header)
    out.append("  " + "─" * (len(header) - 2))

    order = [c for c in CATEGORIES if c in rows] + [c for c in rows if c not in CATEGORIES]
    total = 0
    for cat in order:
        f = rows[cat]
        total += f.n
        negative = cat == "negative_control"
        recall = "n/a" if negative else _cell(mean(f.recall), f.recall)
        mrr_c = "n/a" if negative else _cell(mean(f.rr), f.rr)
        prec = "n/a" if negative else _cell(mean(f.precision), f.precision)
        marker = "   ← the one that matters" if negative else ""
        out.append(
            f"  {cat:<24}{f.n:>4}  {recall:>12}{mrr_c:>12}{prec:>12}"
            f"{f.rate('grounded').render():>14}{f.rate('abstention_correct').render():>14}{marker}"
        )

    out.append("  " + "─" * (len(header) - 2))
    out.append(f"  {'TOTAL':<24}{total:>4}")
    out.append("")

    out.append("  Deterministic checks, by category")
    for cat in order:
        f = rows[cat]
        parts = [f"{n.replace('_', ' ')}: {f.rate(n).render()}" for n in CHECK_COLUMNS
                 if f.rate(n).n_total]
        out.append(f"    {cat}")
        for p in parts:
            out.append(f"      · {p}")
    out.append("")
    out.append("  Reading: `0.75 (4)` = value over 4 cases with data · `n/a` = not verifiable")
    out.append("  (the system did not expose the input, or the category admits no such metric).")
    out.append("  No `n/a` cell counts as either a pass or a failure.")

    errors = sum(f.errors for f in rows.values())
    if errors:
        out.append(f"  {errors} case(s) with a system error: excluded from every metric.")
    out.append("")
    return "\n".join(out)
