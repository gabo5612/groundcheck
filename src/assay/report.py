"""Reporte con desglose por categoria — el producto del harness.

Un numero global ("78% de exactitud") no sirve para decidir nada. Lo que se publica es el
desglose: cuanto recall en preguntas de tabla, cuanta abstencion en los controles
negativos, cuanta groundedness en las alfanumericas. Eso nombra QUE arreglar.

Dos reglas de honestidad implementadas acá:

1. **El reporte re-carga la suite y compara su sha256 contra el que guardo la corrida.**
   Si no coincide, se niega a reportar. Sin esto, alguien podria correr el eval, ver que
   sale mal, ablandar el golden set y reportar el mismo JSON como si nada — que es
   exactamente el fracaso silencioso que este proyecto existe para impedir.

2. **Cada celda lleva su denominador.** Una tasa de groundedness de 1.00 sobre 2 casos
   verificables de 8 no es lo mismo que sobre 8 de 8, y un promedio sin n es una opinion
   con decimales.
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
    """Una tasa con su denominador. `n_verificable` puede ser 0: entonces no hay tasa."""

    aciertos: int = 0
    n_verificable: int = 0
    n_total: int = 0

    @property
    def value(self) -> float | None:
        return None if self.n_verificable == 0 else self.aciertos / self.n_verificable

    def render(self) -> str:
        if self.n_verificable == 0:
            return "n/a"
        return f"{self.value:.2f} ({self.aciertos}/{self.n_verificable})"


@dataclass
class CategoryRow:
    category: str
    n: int = 0
    recall: list[float | None] = field(default_factory=list)
    precision: list[float | None] = field(default_factory=list)
    rr: list[float | None] = field(default_factory=list)
    checks: dict[str, Rate] = field(default_factory=dict)
    errores: int = 0

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
    )


def load_run(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text("utf-8"))


def resolve_suite(run: dict[str, Any], *, suite_path: str | Path | None = None) -> Suite:
    """Carga la suite de la corrida y **verifica su sha256**."""
    declarado = run["suite"]["sha256"]
    path = Path(suite_path or run["suite"]["path"])
    if not path.exists():
        raise ReportError(
            f"no encuentro la suite {path} que uso la corrida. Pasala con --suite si se movio."
        )
    suite = load_suite(path)
    if suite.sha256 != declarado:
        raise ReportError(
            "el golden set CAMBIO desde esta corrida y el reporte seria mentira.\n"
            f"  corrida : {declarado[:16]}…\n"
            f"  archivo : {suite.sha256[:16]}…\n"
            "Volve a correr `assay run` con el set actual, o reporta contra el commit del set."
        )
    return suite


def aggregate(run: dict[str, Any], suite: Suite, *, k: int = 5) -> dict[str, CategoryRow]:
    casos: dict[str, Case] = {c.id: c for c in suite.cases}
    filas: dict[str, CategoryRow] = {}

    for obs in run["observations"]:
        caso = casos.get(obs["case_id"])
        if caso is None:
            raise ReportError(f"la corrida trae un caso {obs['case_id']!r} que no esta en la suite")
        fila = filas.setdefault(caso.category, CategoryRow(category=caso.category))
        fila.n += 1

        if obs.get("error"):
            fila.errores += 1
            continue

        response = _response_from_json(obs.get("response"))
        objetivos = caso.targets()
        items = [
            RetrievedItem.from_raw(r, i)
            for i, r in enumerate((response.retrieved if response else ()), start=1)
        ]
        fila.recall.append(recall_at_k(items, objetivos, k))
        fila.precision.append(precision_at_k(items, objetivos, k))
        fila.rr.append(reciprocal_rank(items, objetivos))

        for nombre, res in evaluate(caso, response).items():
            r = fila.rate(nombre)
            r.n_total += 1
            if res.passed is not None:
                r.n_verificable += 1
                r.aciertos += int(res.passed)

    return filas


def _cell(value: float | None, muestras: list[float | None]) -> str:
    if value is None:
        return "n/a"
    n = sum(1 for v in muestras if v is not None)
    return f"{value:.2f} ({n})"


def render(run: dict[str, Any], filas: dict[str, CategoryRow], *, k: int = 5) -> str:
    sistema = run["system"]
    out: list[str] = []

    out.append("")
    out.append(f"  suite      {run['suite']['name']}  ·  sha256 {run['suite']['sha256'][:16]}…")
    out.append(f"  sistema    {sistema['kind']}  ·  {sistema['target']}")
    out.append(f"  corrida    {run['started_at']}  ·  assay {run['assay_version']} ({run['stage']})")
    if sistema["kind"] == "mock":
        # Sin esto, la tabla de una corrida contra un mock se captura y termina en un
        # portfolio como si fuera una medicion del sistema real.
        out.append("")
        out.append("  ⚠️  SISTEMA GUIONADO (mock): estos numeros miden al mock, NO a un RAG real.")
    out.append("")

    cab = f"  {'categoria':<24}{'n':>4}  {f'recall@{k}':>12}{'MRR':>12}{f'prec@{k}':>12}" \
          f"{'grounded':>14}{'abstencion':>14}"
    out.append(cab)
    out.append("  " + "─" * (len(cab) - 2))

    orden = [c for c in CATEGORIES if c in filas] + [c for c in filas if c not in CATEGORIES]
    total = 0
    for cat in orden:
        f = filas[cat]
        total += f.n
        negativo = cat == "negative_control"
        recall = "n/a" if negativo else _cell(mean(f.recall), f.recall)
        mrr_c = "n/a" if negativo else _cell(mean(f.rr), f.rr)
        prec = "n/a" if negativo else _cell(mean(f.precision), f.precision)
        marca = "   ← el que importa" if negativo else ""
        out.append(
            f"  {cat:<24}{f.n:>4}  {recall:>12}{mrr_c:>12}{prec:>12}"
            f"{f.rate('grounded').render():>14}{f.rate('abstention_correct').render():>14}{marca}"
        )

    out.append("  " + "─" * (len(cab) - 2))
    out.append(f"  {'TOTAL':<24}{total:>4}")
    out.append("")

    out.append("  Checks deterministas, por categoria")
    for cat in orden:
        f = filas[cat]
        partes = [f"{n.replace('_', ' ')}: {f.rate(n).render()}" for n in CHECK_COLUMNS
                  if f.rate(n).n_total]
        out.append(f"    {cat}")
        for p in partes:
            out.append(f"      · {p}")
    out.append("")
    out.append("  Lectura: `0.75 (4)` = valor sobre 4 casos con dato · `n/a` = no verificable")
    out.append("  (el sistema no expuso el insumo, o la categoria no admite esa metrica).")
    out.append("  Ninguna celda `n/a` se cuenta como acierto ni como fallo.")

    errores = sum(f.errores for f in filas.values())
    if errores:
        out.append(f"  {errores} caso(s) con error del sistema: excluidos de toda metrica.")
    out.append("")
    return "\n".join(out)
