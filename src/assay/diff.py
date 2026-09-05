"""`assay diff` — compara dos corridas y nombra que se movio.

Division de trabajo con `gate`, a proposito:

  gate  → ¿esto bloquea el build?   Responde con un codigo de salida.
  diff  → ¿que cambio y por que?    Responde con casos concretos.

Un gate que dice "recall@5 cayo 0.25" no alcanza para arreglar nada. Lo accionable es
"cayo porque `alarma-e114` y `nsn-aceite-law` dejaron de traer su chunk de oro". Por eso
`diff` baja al nivel de caso y no se queda en el promedio.
"""

from __future__ import annotations

from typing import Any

from .checks import evaluate
from .flips import Flip, classify_flips
from .metrics import RetrievedItem, mean, recall_at_k, reciprocal_rank
from .report import _response_from_json
from .schema import CATEGORIES, Suite


class DiffError(RuntimeError):
    pass


def _checks_por_caso(run: dict[str, Any], suite: Suite) -> dict[str, dict[str, bool | None]]:
    casos = {c.id: c for c in suite.cases}
    out: dict[str, dict[str, bool | None]] = {}
    for obs in run["observations"]:
        caso = casos.get(obs["case_id"])
        if caso is None:
            continue
        resultados = evaluate(caso, _response_from_json(obs.get("response")))
        out[obs["case_id"]] = {nombre: r.passed for nombre, r in resultados.items()}
    return out


def _retrieval_por_categoria(
    run: dict[str, Any], suite: Suite, k: int
) -> dict[str, dict[str, float | None]]:
    casos = {c.id: c for c in suite.cases}
    acum: dict[str, dict[str, list[float | None]]] = {}
    for obs in run["observations"]:
        caso = casos.get(obs["case_id"])
        if caso is None or caso.category == "negative_control":
            continue
        resp = _response_from_json(obs.get("response"))
        items = [
            RetrievedItem.from_raw(r, i)
            for i, r in enumerate((resp.retrieved if resp else ()), start=1)
        ]
        objetivos = caso.targets()
        fila = acum.setdefault(caso.category, {"recall": [], "rr": []})
        fila["recall"].append(recall_at_k(items, objetivos, k))
        fila["rr"].append(reciprocal_rank(items, objetivos))
    return {
        cat: {f"recall@{k}": mean(v["recall"]), "MRR": mean(v["rr"])} for cat, v in acum.items()
    }


def diff_runs(
    antes: dict[str, Any], despues: dict[str, Any], suite: Suite, *, k: int = 5
) -> tuple[list[Flip], dict[str, dict[str, tuple[float | None, float | None]]]]:
    """Devuelve `(flips, movimiento_de_retrieval_por_categoria)`."""
    if antes["suite"]["sha256"] != despues["suite"]["sha256"]:
        raise DiffError(
            "las dos corridas usaron golden sets distintos: el diff no significa nada.\n"
            f"  antes   : {antes['suite']['sha256'][:16]}…\n"
            f"  despues : {despues['suite']['sha256'][:16]}…"
        )
    if suite.sha256 != antes["suite"]["sha256"]:
        raise DiffError(
            "la suite en disco no es la que usaron las corridas; el diff seria mentira."
        )

    flips = classify_flips(_checks_por_caso(antes, suite), _checks_por_caso(despues, suite))

    ret_a = _retrieval_por_categoria(antes, suite, k)
    ret_d = _retrieval_por_categoria(despues, suite, k)
    movimiento: dict[str, dict[str, tuple[float | None, float | None]]] = {}
    for cat in sorted(set(ret_a) | set(ret_d)):
        fila = {}
        for metrica in (f"recall@{k}", "MRR"):
            a = ret_a.get(cat, {}).get(metrica)
            d = ret_d.get(cat, {}).get(metrica)
            if a != d:
                fila[metrica] = (a, d)
        if fila:
            movimiento[cat] = fila
    return flips, movimiento


def render(
    antes: dict[str, Any],
    despues: dict[str, Any],
    flips: list[Flip],
    movimiento: dict[str, dict[str, tuple[float | None, float | None]]],
    suite: Suite,
    *,
    k: int = 5,
) -> str:
    categoria_de = {c.id: c.category for c in suite.cases}

    def num(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.3f}"

    def val(v: bool | None) -> str:
        return {True: "ok", False: "FALLA", None: "n/a"}[v]

    out = [""]
    out.append(f"  antes    {antes['system']['target']}  ·  {antes['started_at']}")
    out.append(f"  despues  {despues['system']['target']}  ·  {despues['started_at']}")
    out.append(f"  suite    {suite.name} · sha256 {suite.sha256[:16]}…")
    out.append("")

    if not flips and not movimiento:
        out.append("  ✓ las dos corridas son equivalentes: ningun check ni metrica se movio")
        out.append("")
        return "\n".join(out)

    if movimiento:
        out.append("  Retrieval que se movio, por categoria")
        for cat, metricas in movimiento.items():
            for metrica, (a, d) in metricas.items():
                flecha = "↓" if (a or 0) > (d or 0) else "↑"
                out.append(f"    {flecha} {cat}/{metrica}: {num(a)} → {num(d)}")
        out.append("")

    # El agrupamiento por categoria es el punto: nombra DONDE se movio, no solo cuanto.
    por_categoria: dict[str, list[Flip]] = {}
    for f in flips:
        por_categoria.setdefault(categoria_de.get(f.case_id, "(sin categoria)"), []).append(f)

    orden = [c for c in CATEGORIES if c in por_categoria]
    orden += [c for c in por_categoria if c not in orden]

    for cat in orden:
        grupo = por_categoria[cat]
        rompieron = sum(1 for f in grupo if f.kind == "rompio")
        apagaron = sum(1 for f in grupo if f.kind == "se_apago")
        resumen = []
        if rompieron:
            resumen.append(f"{rompieron} rompio")
        if apagaron:
            resumen.append(f"{apagaron} se apago")
        cola = f"  ({', '.join(resumen)})" if resumen else ""
        out.append(f"  {cat}{cola}")
        for f in grupo:
            if f.check == "(caso)":
                out.append(f"    · {f.case_id}: {f.kind}")
            else:
                out.append(
                    f"    · {f.case_id}/{f.check}: {val(f.antes)} → {val(f.despues)}"
                    f"   [{f.kind}]"
                )
        out.append("")

    rompieron = sum(1 for f in flips if f.kind in ("rompio", "se_apago"))
    mejoraron = sum(1 for f in flips if f.kind in ("arreglo", "se_prendio"))
    out.append(f"  {len(flips)} cambio(s): {rompieron} hacia peor · {mejoraron} hacia mejor")
    out.append("  `diff` no bloquea nada: para eso esta `assay gate`.")
    out.append("")
    return "\n".join(out)
