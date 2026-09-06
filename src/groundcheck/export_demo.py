"""Exports a static bundle of a real run so the demo can be served without a server.

What travels and what does NOT:
  YES  the golden set, whole: gold numbers, forbidden numbers, gold sources
  YES  what the system answered, and the chunks it retrieved, with their text
  YES  the checks and the metrics as this library computed them
  NO   the system under test -> the browser cannot run a local model

The demo re-runs the deterministic checks in JavaScript over the same data and compares
its results against the ones exported here. That comparison is the point: if the port
drifts, the page says so instead of quietly showing prettier numbers.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .checks import evaluate
from .metrics import RetrievedItem, mean, mrr, precision_at_k, recall_at_k, reciprocal_rank
from .report import _response_from_json, aggregate, load_run, resolve_suite

K = 5


def _retrieved(response) -> list[dict[str, Any]]:
    out = []
    for rank, raw in enumerate(response.retrieved if response else (), start=1):
        item = RetrievedItem.from_raw(raw, rank)
        out.append(
            {
                "rank": rank,
                "doc_id": item.doc_id,
                "page": item.page,
                "revision": raw.get("revision"),
                "title": raw.get("title"),
                "section": raw.get("section_path"),
                "text": raw.get("text") or raw.get("snippet") or "",
            }
        )
    return out


def build(run_path: Path, suite_path: Path | None = None) -> dict[str, Any]:
    run = load_run(run_path)
    suite = resolve_suite(run, suite_path=suite_path)
    by_id = {c.id: c for c in suite.cases}

    cases = []
    for obs in run["observations"]:
        case = by_id[obs["case_id"]]
        response = _response_from_json(obs.get("response"))
        items = [
            RetrievedItem.from_raw(r, i)
            for i, r in enumerate((response.retrieved if response else ()), start=1)
        ]
        targets = case.targets()
        cases.append(
            {
                "id": case.id,
                "question": case.question,
                "category": case.category,
                "difficulty": case.difficulty,
                "must_abstain": case.must_abstain,
                "gold_answer": case.gold_answer,
                "gold_numbers": list(case.gold_numbers),
                "forbidden_numbers": list(case.forbidden_numbers),
                "forbidden_codes": list(case.forbidden_codes),
                "gold_sources": [
                    {"doc_id": s.doc_id, "revision": s.revision, "pages": list(s.pages)}
                    for s in case.gold_sources
                ],
                "response": {
                    "answer": response.answer if response else None,
                    "abstained": bool(response.abstained) if response else None,
                    "latency_ms": response.latency_ms if response else None,
                    "retrieved": _retrieved(response),
                },
                "metrics": {
                    "recall_at_k": recall_at_k(items, targets, K),
                    "precision_at_k": precision_at_k(items, targets, K),
                    "reciprocal_rank": reciprocal_rank(items, targets),
                },
                "checks": {
                    name: {"passed": res.passed, "detail": res.detail}
                    for name, res in evaluate(case, response).items()
                },
            }
        )

    rows = aggregate(run, suite, k=K)
    categories = [
        {
            "category": name,
            "n": row.n,
            "recall": mean(row.recall),
            "precision": mean(row.precision),
            "mrr": mrr([], []) if not row.rr else mean(row.rr),
            "checks": {
                cname: {"hits": rate.hits, "n": rate.n_verifiable, "total": rate.n_total}
                for cname, rate in sorted(row.checks.items())
            },
        }
        for name, row in rows.items()
    ]

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "k": K,
        "groundcheck_version": run["groundcheck_version"],
        "stage": run["stage"],
        "suite": run["suite"],
        "system": run["system"],
        "started_at": run["started_at"],
        "finished_at": run["finished_at"],
        "cases": cases,
        "categories": categories,
    }


def export(run_path: Path, out: Path, suite_path: Path | None = None) -> dict[str, Any]:
    data = build(run_path, suite_path)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {
        "cases": len(data["cases"]),
        "categories": len(data["categories"]),
        "kb": round(out.stat().st_size / 1024),
    }


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parents[2]
    runs = sorted((root / "runs-shopfloor").glob("*.json"))
    if len(sys.argv) > 1:
        runs = [Path(sys.argv[1])]
    if not runs:
        raise SystemExit("no run to export: pass one as an argument")
    print(export(runs[-1], root / "demo" / "data.json"))
