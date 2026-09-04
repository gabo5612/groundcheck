"""Orquestacion de una corrida.

M0 registra **solo lo observado**: que se pregunto y que contesto el sistema. Ni una
metrica, ni un check. No es una limitacion de la version — es la separacion que hace
que una corrida de hace tres meses se pueda re-evaluar con los checks de hoy, y que
nadie pueda confundir el dato con el juicio sobre el dato.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .adapter import Adapter
from .schema import Observation, RunRecord, Suite

STAGE = "M0"

STAGE_NOTES = [
    "M0: la corrida guarda observaciones crudas. Las metricas de retrieval (M1) y los "
    "checks deterministas de generacion (M2) todavia no existen: por eso este JSON no "
    "trae ni un numero de calidad. Una celda vacia es honesta; un cero no lo seria.",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_suite(suite: Suite, adapter: Adapter, *, on_case=None) -> RunRecord:
    record = RunRecord(
        assay_version=__version__,
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
            # Un fallo del sistema bajo prueba es un dato, no un crash del harness: la
            # corrida sigue y el error queda registrado en el caso. Si abortaramos, un
            # timeout en la pregunta 3 borraria la evidencia de las otras 47.
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
    path.write_text(json.dumps(record.to_json_dict(), indent=2, ensure_ascii=False) + "\n", "utf-8")
    return path
