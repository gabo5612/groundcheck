"""Harness types.

The rule governing this file: a run stores **observations**, not judgements. The
deterministic checks (M2) and the metrics (M1) are derived afterwards from what was
observed. That way an old run can be re-evaluated with new checks without bothering the
system under test again — and nobody can confuse "what the system said" with "what we
decided about what it said".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# The six categories from §3 of the spec. The list is closed on purpose: a misspelled
# category in the YAML has to be an error, not a silent seventh category that later shows
# up with n=1 in the report.
#
# The values keep their Spanish names because they are the identifiers used by the golden
# sets and by every stored run: renaming them would invalidate every baseline on disk.
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
    # Identifiers from another row/entry that, if present, reveal the system answered
    # about the neighbouring item. `forbidden_numbers` cannot cover them: the "115" in
    # E-115 lives inside an identifier and is never extracted as a number.
    forbidden_codes: tuple[str, ...] = ()
    # Plural: a `multi_documento` case has its answer split across several sources, and
    # with a single `gold_source` that category — 10% of the set per §3 — cannot be
    # measured. The YAML accepts either a map or a list of maps.
    gold_sources: tuple[GoldSource, ...] = ()

    def targets(self) -> tuple[tuple[str, tuple[int, ...]], ...]:
        """Gold targets as `(doc_id, pages)`, the shape `metrics` consumes."""
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
    """What the system under test returned. The full adapter contract."""

    answer: str | None
    citations: tuple[dict[str, Any], ...] = ()
    # `retrieved` != `citations`. Retrieved is what entered the context; cited is what the
    # system chose to show. The retrieval metrics (recall@k, MRR, precision@k) are computed
    # over the FORMER; citation accuracy over the latter. Conflating them measures
    # something else and yields a higher number: a system can cite the single good chunk
    # out of twenty and appear to have perfect precision.
    # Empty means "the system does not expose it" -> retrieval metrics report `None`, not
    # zero.
    retrieved: tuple[dict[str, Any], ...] = ()
    abstained: bool = False
    latency_ms: int | None = None
    # Fields the system returns that the contract does not model, kept verbatim.
    # The case that motivated this: anvil explains WHY it abstained in a `reason` field,
    # and the mapping was dropping it. The labelling sheet then showed an empty answer, and
    # a human judging that marks it "wrong" — reasonably, without knowing the system had in
    # fact explained itself. Discarding the explanation turns a correct abstention into
    # something that looks like a failure.
    extra: tuple[tuple[str, Any], ...] = ()

    @property
    def reason(self) -> str | None:
        return dict(self.extra).get("reason")


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
