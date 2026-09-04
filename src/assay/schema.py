"""Tipos del harness.

Regla que gobierna este archivo: una corrida guarda **observaciones**, no juicios.
Los checks deterministas (M2) y las metricas (M1) se derivan despues, a partir de lo
observado. Asi una corrida vieja se puede re-evaluar con checks nuevos sin volver a
molestar al sistema bajo prueba — y nadie puede confundir "lo que el sistema dijo" con
"lo que decidimos sobre lo que dijo".
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# Las seis categorias de §3 del contexto. La lista es cerrada a proposito: una
# categoria mal escrita en el YAML tiene que ser un error, no una septima categoria
# silenciosa que despues aparece con n=1 en el reporte.
CATEGORIES = (
    "factual_lookup",
    "alfanumerico_exacto",
    "procedimental",
    "multi_documento",
    "negative_control",
    "revision_supersedida",
)

DIFFICULTIES = ("easy", "medium", "hard")


@dataclass(frozen=True)
class GoldSource:
    doc_id: str
    revision: str | None = None
    pages: tuple[int, ...] = ()


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    category: str
    must_abstain: bool = False
    difficulty: str | None = None
    languages: tuple[str, ...] = ()
    gold_answer: str | None = None
    gold_numbers: tuple[str, ...] = ()
    forbidden_numbers: tuple[str, ...] = ()
    # Plural: un caso `multi_documento` tiene la respuesta repartida entre varias
    # fuentes, y con un solo `gold_source` esa categoria — 10% del set segun §3 del
    # contexto — no se puede medir. El YAML acepta un mapa o una lista de mapas.
    gold_sources: tuple[GoldSource, ...] = ()

    def targets(self) -> tuple[tuple[str, tuple[int, ...]], ...]:
        """Objetivos de oro como `(doc_id, paginas)`, el formato que consume `metrics`."""
        return tuple((src.doc_id, src.pages) for src in self.gold_sources)


@dataclass(frozen=True)
class Suite:
    name: str
    path: str
    sha256: str
    cases: tuple[Case, ...]

    @property
    def case_count(self) -> int:
        return len(self.cases)

    def category_counts(self) -> dict[str, int]:
        counts = {c: 0 for c in CATEGORIES}
        for case in self.cases:
            counts[case.category] += 1
        return counts


@dataclass(frozen=True)
class Response:
    """Lo que devolvio el sistema bajo prueba. El contrato completo del adaptador."""

    answer: str | None
    citations: tuple[dict[str, Any], ...] = ()
    # `retrieved` != `citations`. Lo recuperado es lo que entro al contexto; lo citado es
    # lo que el sistema eligio mostrar. Las metricas de retrieval (recall@k, MRR,
    # precision@k) se calculan sobre lo PRIMERO; la exactitud de cita, sobre lo segundo.
    # Confundirlos mide otra cosa y da un numero mas alto: un sistema puede citar bien
    # el unico chunk bueno de veinte y aparentar precision perfecta.
    # Vacio significa "el sistema no lo expone" -> las metricas de retrieval quedan en
    # `None`, no en cero.
    retrieved: tuple[dict[str, Any], ...] = ()
    abstained: bool = False
    latency_ms: int | None = None


@dataclass
class Observation:
    case_id: str
    category: str
    question: str
    must_abstain: bool
    response: Response | None = None
    error: str | None = None


@dataclass
class RunRecord:
    assay_version: str
    stage: str
    suite: dict[str, Any]
    system: dict[str, Any]
    started_at: str
    finished_at: str | None = None
    observations: list[Observation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)
