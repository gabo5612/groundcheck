"""Loading and validation of the golden set.

The validator is deliberately severe. The reason: in an evaluation harness a typo does not
produce an error — it produces a **check that silently stops running**. If someone writes
`forbiden_numbers`, the exact check that catches the split-table bug (§3 of the spec)
disappears, the report keeps coming out green, and the published metric becomes a lie. That
is why an unknown key is a hard error and not a warning.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from .schema import CATEGORIES, DIFFICULTIES, Case, GoldSource, Suite

CASE_KEYS = {
    "id",
    "question",
    "category",
    "difficulty",
    "languages",
    "gold_answer",
    "gold_numbers",
    "forbidden_numbers",
    "forbidden_codes",
    "gold_source",
    "must_abstain",
}

SOURCE_KEYS = {"doc_id", "revision", "pages"}


class SuiteError(ValueError):
    """Invalid suite. The message always names the case id and the offending key."""


def _fail(where: str, msg: str) -> None:
    raise SuiteError(f"{where}: {msg}")


def _as_str_tuple(where: str, key: str, value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        _fail(where, f"`{key}` must be a list, not {type(value).__name__}")
    out = []
    for item in value:
        # Numbers are compared literally against the answer's text, so they have to end up
        # as strings. 680 and "680" look the same in YAML but do not compare the same, and
        # that is exactly the kind of bug that raises no error.
        if isinstance(item, bool) or not isinstance(item, (str, int, float)):
            _fail(where, f"`{key}` only accepts strings or numbers, got {item!r}")
        out.append(str(item))
    return tuple(out)


def _parse_sources(where: str, raw: Any) -> tuple[GoldSource, ...]:
    """Accepts a map or a list of maps (required for `multi_documento`)."""
    if raw is None:
        return ()
    if isinstance(raw, dict):
        return (_parse_one_source(where, raw),)
    if isinstance(raw, list):
        if not raw:
            _fail(where, "`gold_source` is an empty list — remove it or fill it in")
        return tuple(_parse_one_source(where, item) for item in raw)
    _fail(where, "`gold_source` must be a map or a list of maps")


def _parse_one_source(where: str, raw: Any) -> GoldSource:
    if not isinstance(raw, dict):
        _fail(where, "each `gold_source` must be a map")
    unknown = set(raw) - SOURCE_KEYS
    if unknown:
        _fail(where, f"unknown keys in `gold_source`: {sorted(unknown)}")
    if "doc_id" not in raw:
        _fail(where, "`gold_source` without `doc_id`")
    pages = raw.get("pages") or []
    if not isinstance(pages, list) or any(not isinstance(p, int) or isinstance(p, bool) for p in pages):
        _fail(where, "`gold_source.pages` must be a list of integers")
    revision = raw.get("revision")
    if revision is not None and not isinstance(revision, (str, int)):
        _fail(where, "`gold_source.revision` must be text")
    return GoldSource(
        doc_id=str(raw["doc_id"]),
        revision=None if revision is None else str(revision),
        pages=tuple(pages),
    )


def _parse_case(index: int, raw: Any) -> Case:
    where = f"case #{index + 1}"
    if not isinstance(raw, dict):
        _fail(where, f"must be a map, not {type(raw).__name__}")

    case_id = raw.get("id")
    if not isinstance(case_id, str) or not case_id.strip():
        _fail(where, "`id` missing or empty")
    where = f"case `{case_id}`"

    unknown = set(raw) - CASE_KEYS
    if unknown:
        _fail(where, f"unknown keys: {sorted(unknown)} — check the spelling")

    question = raw.get("question")
    if not isinstance(question, str) or not question.strip():
        _fail(where, "`question` missing or empty")

    category = raw.get("category")
    if category not in CATEGORIES:
        _fail(where, f"invalid `category` {category!r}; valid: {list(CATEGORIES)}")

    difficulty = raw.get("difficulty")
    if difficulty is not None and difficulty not in DIFFICULTIES:
        _fail(where, f"invalid `difficulty` {difficulty!r}; valid: {list(DIFFICULTIES)}")

    must_abstain = raw.get("must_abstain", category == "negative_control")
    if not isinstance(must_abstain, bool):
        _fail(where, "`must_abstain` must be true or false")

    gold_answer = raw.get("gold_answer")
    if gold_answer is not None and not isinstance(gold_answer, str):
        _fail(where, "`gold_answer` must be text or null")

    # The two contradictions that make the 20% of negative controls measure nothing.
    if category == "negative_control":
        if not must_abstain:
            _fail(where, "a `negative_control` with `must_abstain: false` proves nothing")
        if gold_answer is not None:
            _fail(where, "a `negative_control` cannot have a `gold_answer`")
    elif must_abstain:
        _fail(where, "`must_abstain: true` outside `negative_control` — wrong category?")

    languages = _as_str_tuple(where, "languages", raw.get("languages"))
    gold_numbers = _as_str_tuple(where, "gold_numbers", raw.get("gold_numbers"))
    forbidden = _as_str_tuple(where, "forbidden_numbers", raw.get("forbidden_numbers"))
    forbidden_codes = _as_str_tuple(where, "forbidden_codes", raw.get("forbidden_codes"))

    # A forbidden code appearing in the gold answer would be a trap against the correct
    # answer: the case would always fail, whatever the system did.
    if case.get("gold_answer") if isinstance(case := raw, dict) else False:
        from .numbers import extract_codes

        in_gold = {c.upper() for c in extract_codes(raw.get("gold_answer") or "")}
        clash = sorted({c.upper() for c in forbidden_codes} & in_gold)
        if clash:
            _fail(where, f"{clash} is in both `forbidden_codes` and `gold_answer`")

    sources = _parse_sources(where, raw.get("gold_source"))
    if category == "multi_documento" and len({s.doc_id for s in sources}) < 2:
        _fail(
            where,
            "`multi_documento` with fewer than two distinct `doc_id`s proves no synthesis "
            "across sources — either add the other source or change the category",
        )

    overlap = set(gold_numbers) & set(forbidden)
    if overlap:
        _fail(where, f"{sorted(overlap)} is in both `gold_numbers` and `forbidden_numbers`")

    return Case(
        id=case_id,
        question=question,
        category=category,
        must_abstain=must_abstain,
        difficulty=difficulty,
        languages=languages,
        gold_answer=gold_answer,
        gold_numbers=gold_numbers,
        forbidden_numbers=forbidden,
        forbidden_codes=forbidden_codes,
        gold_sources=_parse_sources(where, raw.get("gold_source")),
    )


def load_suite(path: str | Path) -> Suite:
    p = Path(path)
    raw_bytes = p.read_bytes()
    # The sha goes into every run. It is what lets you prove to a third party that the set
    # measured with is the one committed, and not a softened version.
    sha = hashlib.sha256(raw_bytes).hexdigest()

    doc = yaml.safe_load(raw_bytes.decode("utf-8"))
    if isinstance(doc, dict):
        name = str(doc.get("name") or p.stem)
        raw_cases = doc.get("cases")
    elif isinstance(doc, list):
        name, raw_cases = p.stem, doc
    else:
        raise SuiteError(f"{p}: the suite must be a list of cases or a map with `cases`")

    if not isinstance(raw_cases, list) or not raw_cases:
        raise SuiteError(f"{p}: `cases` empty or missing")

    cases = tuple(_parse_case(i, raw) for i, raw in enumerate(raw_cases))

    seen: dict[str, int] = {}
    for i, case in enumerate(cases):
        if case.id in seen:
            raise SuiteError(
                f"{p}: duplicate id `{case.id}` (cases #{seen[case.id] + 1} and #{i + 1})"
            )
        seen[case.id] = i

    return Suite(name=name, path=str(p), sha256=sha, cases=cases)
