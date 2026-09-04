"""Carga y validacion del golden set.

El validador es deliberadamente severo. La razon: en un harness de evals, un typo no
produce un error — produce un **check que deja de correr en silencio**. Si alguien
escribe `forbiden_numbers`, se pierde exactamente la comprobacion que atrapa el bug de
la tabla partida (§3 del contexto), el reporte sigue saliendo verde, y la metrica
publicada pasa a ser mentira. Por eso una clave desconocida es un error duro y no una
advertencia.
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
    "gold_source",
    "must_abstain",
}

SOURCE_KEYS = {"doc_id", "revision", "pages"}


class SuiteError(ValueError):
    """Suite invalida. El mensaje siempre dice el id del caso y la clave culpable."""


def _fail(where: str, msg: str) -> None:
    raise SuiteError(f"{where}: {msg}")


def _as_str_tuple(where: str, key: str, value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        _fail(where, f"`{key}` tiene que ser una lista, no {type(value).__name__}")
    out = []
    for item in value:
        # Los numeros se comparan como literales contra el texto de la respuesta, asi que
        # tienen que quedar como string. 680 y "680" se ven igual en YAML pero no
        # comparan igual, y ese es justo el tipo de bug que no da error.
        if isinstance(item, bool) or not isinstance(item, (str, int, float)):
            _fail(where, f"`{key}` solo acepta strings o numeros, vino {item!r}")
        out.append(str(item))
    return tuple(out)


def _parse_sources(where: str, raw: Any) -> tuple[GoldSource, ...]:
    """Acepta un mapa o una lista de mapas (necesario para `multi_documento`)."""
    if raw is None:
        return ()
    if isinstance(raw, dict):
        return (_parse_one_source(where, raw),)
    if isinstance(raw, list):
        if not raw:
            _fail(where, "`gold_source` es una lista vacia — quitala o completala")
        return tuple(_parse_one_source(where, item) for item in raw)
    _fail(where, "`gold_source` tiene que ser un mapa o una lista de mapas")


def _parse_one_source(where: str, raw: Any) -> GoldSource:
    if not isinstance(raw, dict):
        _fail(where, "cada `gold_source` tiene que ser un mapa")
    unknown = set(raw) - SOURCE_KEYS
    if unknown:
        _fail(where, f"claves desconocidas en `gold_source`: {sorted(unknown)}")
    if "doc_id" not in raw:
        _fail(where, "`gold_source` sin `doc_id`")
    pages = raw.get("pages") or []
    if not isinstance(pages, list) or any(not isinstance(p, int) or isinstance(p, bool) for p in pages):
        _fail(where, "`gold_source.pages` tiene que ser una lista de enteros")
    revision = raw.get("revision")
    if revision is not None and not isinstance(revision, (str, int)):
        _fail(where, "`gold_source.revision` tiene que ser texto")
    return GoldSource(
        doc_id=str(raw["doc_id"]),
        revision=None if revision is None else str(revision),
        pages=tuple(pages),
    )


def _parse_case(index: int, raw: Any) -> Case:
    where = f"caso #{index + 1}"
    if not isinstance(raw, dict):
        _fail(where, f"tiene que ser un mapa, no {type(raw).__name__}")

    case_id = raw.get("id")
    if not isinstance(case_id, str) or not case_id.strip():
        _fail(where, "`id` faltante o vacio")
    where = f"caso `{case_id}`"

    unknown = set(raw) - CASE_KEYS
    if unknown:
        _fail(where, f"claves desconocidas: {sorted(unknown)} — revisa la ortografia")

    question = raw.get("question")
    if not isinstance(question, str) or not question.strip():
        _fail(where, "`question` faltante o vacia")

    category = raw.get("category")
    if category not in CATEGORIES:
        _fail(where, f"`category` invalida {category!r}; validas: {list(CATEGORIES)}")

    difficulty = raw.get("difficulty")
    if difficulty is not None and difficulty not in DIFFICULTIES:
        _fail(where, f"`difficulty` invalida {difficulty!r}; validas: {list(DIFFICULTIES)}")

    must_abstain = raw.get("must_abstain", category == "negative_control")
    if not isinstance(must_abstain, bool):
        _fail(where, "`must_abstain` tiene que ser true o false")

    gold_answer = raw.get("gold_answer")
    if gold_answer is not None and not isinstance(gold_answer, str):
        _fail(where, "`gold_answer` tiene que ser texto o null")

    # Las dos contradicciones que hacen que el 20% de controles negativos no mida nada.
    if category == "negative_control":
        if not must_abstain:
            _fail(where, "un `negative_control` con `must_abstain: false` no prueba nada")
        if gold_answer is not None:
            _fail(where, "un `negative_control` no puede tener `gold_answer`")
    elif must_abstain:
        _fail(where, "`must_abstain: true` fuera de `negative_control` — categoria equivocada?")

    languages = _as_str_tuple(where, "languages", raw.get("languages"))
    gold_numbers = _as_str_tuple(where, "gold_numbers", raw.get("gold_numbers"))
    forbidden = _as_str_tuple(where, "forbidden_numbers", raw.get("forbidden_numbers"))

    sources = _parse_sources(where, raw.get("gold_source"))
    if category == "multi_documento" and len({s.doc_id for s in sources}) < 2:
        _fail(
            where,
            "`multi_documento` con menos de dos `doc_id` distintos no prueba sintesis "
            "entre fuentes — o agrega la otra fuente, o cambia la categoria",
        )

    overlap = set(gold_numbers) & set(forbidden)
    if overlap:
        _fail(where, f"{sorted(overlap)} esta en `gold_numbers` y en `forbidden_numbers` a la vez")

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
        gold_sources=_parse_sources(where, raw.get("gold_source")),
    )


def load_suite(path: str | Path) -> Suite:
    p = Path(path)
    raw_bytes = p.read_bytes()
    # El sha va en cada corrida. Es lo que permite probarle a un tercero que el set con
    # el que se midio es el mismo que esta commiteado, y no una version ablandada.
    sha = hashlib.sha256(raw_bytes).hexdigest()

    doc = yaml.safe_load(raw_bytes.decode("utf-8"))
    if isinstance(doc, dict):
        name = str(doc.get("name") or p.stem)
        raw_cases = doc.get("cases")
    elif isinstance(doc, list):
        name, raw_cases = p.stem, doc
    else:
        raise SuiteError(f"{p}: la suite tiene que ser una lista de casos o un mapa con `cases`")

    if not isinstance(raw_cases, list) or not raw_cases:
        raise SuiteError(f"{p}: `cases` vacio o ausente")

    cases = tuple(_parse_case(i, raw) for i, raw in enumerate(raw_cases))

    seen: dict[str, int] = {}
    for i, case in enumerate(cases):
        if case.id in seen:
            raise SuiteError(
                f"{p}: id duplicado `{case.id}` (casos #{seen[case.id] + 1} y #{i + 1})"
            )
        seen[case.id] = i

    return Suite(name=name, path=str(p), sha256=sha, cases=cases)
