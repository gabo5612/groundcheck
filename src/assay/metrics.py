"""Metricas de retrieval. Operaciones de conjuntos, sin un modelo de por medio.

Tres decisiones estan escritas explicitas acá porque son exactamente las que, tomadas en
silencio, hacen que dos corridas dejen de ser comparables y nadie se entere:

1. **`precision_at_k` divide por `k`, no por la cantidad recuperada.** Es la definicion
   estandar de IR. Un sistema que devuelve 3 chunks con k=5 se lleva un castigo real, y
   eso es correcto: pidio menos contexto del disponible. La cantidad recuperada queda
   registrada aparte para que cualquiera pueda recalcular con la otra convencion.
2. **`recall_at_k` cuenta objetivos cubiertos, no items relevantes.** Con dos paginas de
   oro y las dos en el top-k, es 1.0; con una sola, 0.5. Contar items relevantes daria
   1.0 tambien en el segundo caso si el mismo chunk apareciera dos veces — y ese es el
   bug clasico que infla el numero.
3. **Los controles negativos no tienen metricas de retrieval: devuelven `None`.** No un
   cero. Un cero se promedia y arrastra la media hacia abajo con un dato que no existe;
   `None` obliga a que el reporte diga `n/a`, que es la verdad.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class RetrievedItem:
    """Un chunk recuperado. `rank` es 1-based: `rank=1` es el primero."""

    rank: int
    doc_id: str | None = None
    page: int | None = None
    chunk_id: str | None = None
    revision: str | None = None

    @staticmethod
    def from_raw(raw: Any, rank: int) -> "RetrievedItem":
        if not isinstance(raw, dict):
            return RetrievedItem(rank=rank, chunk_id=str(raw))
        page = raw.get("page")
        if isinstance(page, bool) or not isinstance(page, int):
            page = None
        return RetrievedItem(
            rank=rank,
            doc_id=None if raw.get("doc_id") is None else str(raw["doc_id"]),
            page=page,
            chunk_id=None if raw.get("chunk_id") is None else str(raw["chunk_id"]),
            revision=None if raw.get("revision") is None else str(raw["revision"]),
        )


def matches(item: RetrievedItem, doc_id: str, pages: Sequence[int]) -> bool:
    """Un item recuperado cubre un objetivo de oro?

    Si el objetivo especifica paginas y el item no reporta la suya, **no cuenta**. Un
    sistema que no dice en que pagina encontro algo no puede acreditarse recall a nivel
    de pagina: seria darle credito por informacion que no entrego.
    """
    if item.doc_id is None or item.doc_id != doc_id:
        return False
    if not pages:
        return True
    return item.page is not None and item.page in pages


def relevance_vector(
    retrieved: Sequence[RetrievedItem], targets: Sequence[tuple[str, Sequence[int]]]
) -> list[bool]:
    """Para cada item en orden de rank: cubre algun objetivo?"""
    return [any(matches(item, doc, pages) for doc, pages in targets) for item in retrieved]


def recall_at_k(
    retrieved: Sequence[RetrievedItem],
    targets: Sequence[tuple[str, Sequence[int]]],
    k: int,
) -> float | None:
    """Fraccion de objetivos de oro cubiertos por el top-k. `None` si no hay objetivos."""
    if k <= 0:
        raise ValueError("k tiene que ser >= 1")
    if not targets:
        return None
    top = retrieved[:k]
    cubiertos = sum(1 for doc, pages in targets if any(matches(i, doc, pages) for i in top))
    return cubiertos / len(targets)


def precision_at_k(
    retrieved: Sequence[RetrievedItem],
    targets: Sequence[tuple[str, Sequence[int]]],
    k: int,
) -> float | None:
    """Fraccion del top-k que es relevante. Divide por `k` (ver decision 1 del modulo)."""
    if k <= 0:
        raise ValueError("k tiene que ser >= 1")
    if not targets:
        return None
    relevantes = sum(relevance_vector(retrieved[:k], targets))
    return relevantes / k


def reciprocal_rank(
    retrieved: Sequence[RetrievedItem], targets: Sequence[tuple[str, Sequence[int]]]
) -> float | None:
    """1 / posicion del primer item relevante. `0.0` si ninguno lo es."""
    if not targets:
        return None
    for pos, relevante in enumerate(relevance_vector(retrieved, targets), start=1):
        if relevante:
            return 1.0 / pos
    return 0.0


def mean(values: Iterable[float | None]) -> float | None:
    """Promedio que **ignora** los `None` en vez de tratarlos como cero.

    Es el corolario de la decision 3: si de 20 casos 4 son controles negativos, el
    recall promedio se calcula sobre 16, no sobre 20.
    """
    presentes = [v for v in values if v is not None]
    if not presentes:
        return None
    return sum(presentes) / len(presentes)


def mrr(retrieved_per_case, targets_per_case) -> float | None:
    """Mean Reciprocal Rank sobre varios casos."""
    return mean(
        reciprocal_rank(r, t) for r, t in zip(retrieved_per_case, targets_per_case, strict=True)
    )
