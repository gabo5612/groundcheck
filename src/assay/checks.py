"""Deterministic generation checks.

All of them are set operations and normalised string comparisons. No model participates:
the design rule from §4 of the spec is that the deterministic part blocks CI and the fuzzy
part is only reported.

Three states per check, and the distinction between the last two is the heart of this
module:

- `True`  — verified and passes
- `False` — verified and **fails**
- `None`  — **could not be verified** (the input is missing: the system did not expose the
            cited chunk's text, or the case defines no gold numbers)

`None` never counts as a failure nor as a success. A harness that turns "I could not
verify" into "it failed" pushes you to fix things that were not broken; one that turns it
into "it passes" publishes a number that measured nothing. That is why the report shows
them separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .metrics import RetrievedItem, matches
from .numbers import contains_code, contains_number, extract_codes, extract_numbers
from .schema import Case, Response


@dataclass
class CheckResult:
    name: str
    passed: bool | None
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def verifiable(self) -> bool:
        return self.passed is not None


# ── abstention phrases ───────────────────────────────────────────────────────
# A phrase list, not a model. §8 of the spec says so explicitly: start with a list plus
# manual review of the disagreements, without putting a model in charge of deciding
# whether another model abstained. The list is visible and auditable; a classifier would
# be a black box inside the verifier itself.
#
# Phrases stay in both Spanish and English because the systems under test answer in the
# language of their corpus.
ABSTENTION_PHRASES = (
    "no encontre", "no encontré", "no aparece", "no figura", "no dispongo",
    "no tengo informacion", "no tengo información", "no hay informacion",
    "no hay información", "no se especifica", "no esta especificado",
    "no está especificado", "no puedo confirmar", "no consta",
    "i could not find", "i don't have", "i do not have", "not specified",
    "no information", "cannot confirm", "not found in",
)


def looks_like_abstention(answer: str | None) -> bool:
    if answer is None or not answer.strip():
        return True
    low = answer.lower()
    return any(p in low for p in ABSTENTION_PHRASES)


def _citation_texts(response: Response) -> list[str]:
    """Text of the cited chunks, when the system exposes it."""
    out = []
    for c in response.citations:
        text = c.get("text") or c.get("snippet") or c.get("content")
        if isinstance(text, str) and text.strip():
            out.append(text)
    return out


# ── the checks ───────────────────────────────────────────────────────────────
def check_gold_numbers(case: Case, response: Response) -> CheckResult:
    """Every `gold_number` appears literally in the answer."""
    if not case.gold_numbers:
        return CheckResult("gold_numbers_present", None, "the case defines no gold numbers")
    if response.abstained:
        return CheckResult(
            "gold_numbers_present", False, "abstained on a case that does have an answer"
        )
    missing = [n for n in case.gold_numbers if not contains_number(response.answer, n)]
    return CheckResult(
        "gold_numbers_present",
        not missing,
        "all present" if not missing else f"missing {missing}",
        {"expected": list(case.gold_numbers), "missing": missing},
    )


def check_forbidden_numbers(case: Case, response: Response) -> CheckResult:
    """No `forbidden_number` appears in the answer.

    This is the check that catches the split-table bug: if the answer carries 950 when it
    should carry 720, that is not "a slightly different answer" — it crossed rows.
    """
    if not case.forbidden_numbers:
        return CheckResult("forbidden_numbers_absent", None, "the case defines none")
    present = [n for n in case.forbidden_numbers if contains_number(response.answer, n)]
    return CheckResult(
        "forbidden_numbers_absent",
        not present,
        "none present" if not present else f"{present} appear — it crossed rows",
        {"forbidden": list(case.forbidden_numbers), "present": present},
    )


def check_forbidden_codes(case: Case, response: Response) -> CheckResult:
    """No forbidden identifier appears in the answer.

    The sibling of `check_forbidden_numbers` for the alphanumeric world. The typical trap
    in `alfanumerico_exacto`: ask about alarm E-114 and get the description of E-115.
    `forbidden_numbers` cannot see it — the "115" is never extracted as a number because
    it lives inside an identifier.
    """
    if not case.forbidden_codes:
        return CheckResult("forbidden_codes_absent", None, "the case defines no forbidden codes")
    present = [c for c in case.forbidden_codes if contains_code(response.answer, c)]
    return CheckResult(
        "forbidden_codes_absent",
        not present,
        "none present" if not present else f"{present} appear — it answered about the neighbour",
        {"forbidden": list(case.forbidden_codes), "present": present},
    )


def check_grounded(case: Case, response: Response) -> CheckResult:
    """Every number and code in the answer appears literally in some cited chunk.

    Without the chunks' text this cannot be verified, and in that case it returns `None`:
    saying "not grounded" because the system does not expose its chunks would blame it for
    something that was never measured.

    **Numbers and codes that were already in the question are exempt.** Groundedness asks
    whether the system *introduced* an unsupported fact; a fact the user typed was not
    introduced by the system. Without this exemption, answering "the 15 mm A516 needs no
    preheating" fails because the "15" is not in the table — and repeating the question is
    not hallucinating. (Found while filling in the M4 report.)

    The negative control does not escape through this door: if the question asks about bolt
    M30, the `M30` is exempt but any torque it invents still has to be in the chunk, and
    abstention is handled by `check_abstention`, which is its own check.
    """
    if response.abstained:
        return CheckResult("grounded", None, "abstained: there is nothing to ground")

    texts = _citation_texts(response)
    if not texts:
        return CheckResult(
            "grounded",
            None,
            "citations carry no text — the system does not expose chunk content",
            {"citations": len(response.citations)},
        )

    corpus = "\n".join(texts)
    numbers = extract_numbers(response.answer)
    codes = extract_codes(response.answer)

    # Question exemption: whatever was already in the question was not introduced by the
    # system.
    question_numbers = {t.canonical for t in extract_numbers(case.question)}
    question_codes = set(extract_codes(case.question))

    orphan_numbers = [
        t.raw
        for t in numbers
        if t.canonical not in question_numbers and not contains_number(corpus, t.raw)
    ]
    corpus_codes = set(extract_codes(corpus))
    orphan_codes = [c for c in codes if c not in question_codes and c not in corpus_codes]

    orphans = orphan_numbers + orphan_codes
    if not numbers and not codes:
        return CheckResult(
            "grounded", None, "the answer carries no numbers or codes to verify"
        )
    return CheckResult(
        "grounded",
        not orphans,
        "fully grounded" if not orphans else f"unsupported: {orphans}",
        {
            "numbers_in_answer": [t.raw for t in numbers],
            "codes_in_answer": codes,
            "exempt_because_in_question": sorted(question_numbers | question_codes),
            "unsupported": orphans,
        },
    )


def check_citation_hits_gold(case: Case, response: Response) -> CheckResult:
    """Some citation points at the gold document/page."""
    targets = case.targets()
    if not targets:
        return CheckResult("citation_hits_gold", None, "the case defines no gold source")
    if not response.citations:
        return CheckResult("citation_hits_gold", False, "it cited nothing")

    items = [RetrievedItem.from_raw(c, i) for i, c in enumerate(response.citations, start=1)]
    hits = [
        {"doc_id": it.doc_id, "page": it.page}
        for it in items
        if any(matches(it, doc, pages) for doc, pages in targets)
    ]
    return CheckResult(
        "citation_hits_gold",
        bool(hits),
        "correct citation" if hits else "no citation points at the gold source",
        {"targets": [{"doc_id": d, "pages": list(p)} for d, p in targets], "hits": hits},
    )


def check_abstention(case: Case, response: Response) -> CheckResult:
    """On negative controls it abstained. On the rest it answered.

    The most important metric in the set: without it, a system that always answers
    confidently scores perfect.
    """
    declared = response.abstained
    by_phrase = looks_like_abstention(response.answer)
    abstained = declared or by_phrase

    if case.must_abstain:
        return CheckResult(
            "abstention_correct",
            abstained,
            "abstained, correct" if abstained
            else "HALLUCINATED: answered a question that has no answer",
            {"declared": declared, "by_phrase": by_phrase, "expected": "abstain"},
        )
    return CheckResult(
        "abstention_correct",
        not abstained,
        "answered, correct" if not abstained
        else "abstained on a case that does have an answer",
        {"declared": declared, "by_phrase": by_phrase, "expected": "answer"},
    )


def check_revision_current(case: Case, response: Response) -> CheckResult:
    """It cited the current revision rather than a superseded one."""
    gold_revisions = {s.revision for s in case.gold_sources if s.revision}
    if not gold_revisions:
        return CheckResult("revision_current", None, "the case pins no gold revision")

    cited = {str(c["revision"]) for c in response.citations if c.get("revision") is not None}
    if not cited:
        return CheckResult(
            "revision_current", None, "citations report no revision — cannot verify"
        )

    stale = cited - gold_revisions
    return CheckResult(
        "revision_current",
        not stale,
        "current revision" if not stale else f"cited a superseded revision: {sorted(stale)}",
        {"current": sorted(gold_revisions), "cited": sorted(cited)},
    )


CHECKS = (
    check_gold_numbers,
    check_forbidden_numbers,
    check_forbidden_codes,
    check_grounded,
    check_citation_hits_gold,
    check_abstention,
    check_revision_current,
)


def evaluate(case: Case, response: Response | None) -> dict[str, CheckResult]:
    """Every check on one case. With no response, all of them stay unverified."""
    if response is None:
        return {
            fn(case, Response(answer=None)).name: CheckResult(
                fn(case, Response(answer=None)).name, None, "the system did not answer (error)"
            )
            for fn in CHECKS
        }
    results = [fn(case, response) for fn in CHECKS]
    return {r.name: r for r in results}
