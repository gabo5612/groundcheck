"""Run orchestration.

A run records **only what was observed**: what was asked and what the system answered. Not
one metric, not one check. That is not a limitation of the current version — it is the
separation that lets a three-month-old run be re-evaluated with today's checks, and that
stops anyone confusing the data with the judgement about the data.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .adapter import Adapter
from .schema import Observation, RunRecord, Suite

STAGE = "M4"

STAGE_NOTES = [
    "A run stores raw observations and NO metrics, by design. Retrieval metrics and the "
    "deterministic checks are derived afterwards by `groundcheck report`, which verifies the "
    "golden set's sha256 before reporting. That way an old run can be re-evaluated with "
    "new checks, and nobody confuses the data with the judgement about the data.",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_suite(suite: Suite, adapter: Adapter, *, on_case=None) -> RunRecord:
    record = RunRecord(
        groundcheck_version=__version__,
        stage=STAGE,
        suite={
            "name": suite.name,
            "path": suite.path,
            "sha256": suite.sha256,
            "case_count": suite.case_count,
            "category_counts": suite.category_counts(),
        },
        system={"kind": adapter.kind, "target": adapter.target},
        started_at=_now(),
        notes=list(STAGE_NOTES),
    )

    for case in suite.cases:
        obs = Observation(
            case_id=case.id,
            category=case.category,
            question=case.question,
            must_abstain=case.must_abstain,
        )
        try:
            obs.response = adapter.ask(case.question)
        except Exception as exc:
            # A failure of the system under test is data, not a harness crash: the run
            # continues and the error is recorded on the case. If we aborted, a timeout on
            # question 3 would erase the evidence from the other 47.
            obs.error = f"{type(exc).__name__}: {exc}"
        record.observations.append(obs)
        if on_case is not None:
            on_case(obs)

    record.finished_at = _now()
    return record


def write_run(record: RunRecord, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = record.started_at.replace(":", "-").replace("+00:00", "Z")
    path = out / f"{stamp}.json"
    # Two runs in the same second must NOT overwrite each other. The filename has
    # second resolution, and losing a run silently is worse than an ugly name: you run the
    # baseline and the new version back to back, and the diff compares a run against
    # itself reporting "no changes" — the most expensive lie this harness can tell.
    suffix = 2
    while path.exists():
        path = out / f"{stamp}-{suffix}.json"
        suffix += 1
    path.write_text(json.dumps(record.to_json_dict(), indent=2, ensure_ascii=False) + "\n", "utf-8")
    return path
