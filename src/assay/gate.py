"""Gate de CI: falla el build cuando una metrica se degrada.

Es la pieza que convierte el harness en algo que *protege*, y no solo en un reporte que
alguien mira cuando se acuerda. Sin gate, la secuencia real es: alguien cambia el tamano
de chunk, la exactitud numerica baja un 12%, nadie corre el eval, y el sistema queda peor
sin que exista un momento en el que eso se note.

Cuatro decisiones, cada una con su test:

1. **Se niega a comparar si el golden set cambio.** Comparar contra un baseline medido con
   otro set no es una comparacion, es una coincidencia. Se compara el sha256.
2. **Se niega a comparar si el `k` no coincide.** recall@1 contra recall@5 daria una
   "regresion" inventada por el parametro, no por el sistema.
3. **Perder la capacidad de verificar es una regresion.** Si el baseline tenia
   `grounded 0.90 (10/10)` y ahora dice `n/a` porque el sistema dejo de exponer el texto
   de sus chunks, el numero no "se mantuvo": desaparecio. Eso falla. Es la forma mas
   silenciosa de que una metrica deje de significar algo.
4. **Una mejora nunca falla el gate**, y se imprime igual: un salto grande hacia arriba
   suele ser un bug en el eval, no un milagro del sistema.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_MAX_REGRESSION = 0.02


class GateError(RuntimeError):
    pass


@dataclass(frozen=True)
class Finding:
    category: str
    metric: str
    baseline: float | None
    current: float | None
    kind: str          # "regresion" · "verificabilidad" · "mejora" · "nuevo"
    detail: str

    @property
    def blocks(self) -> bool:
        return self.kind in ("regresion", "verificabilidad")

    @property
    def delta(self) -> float | None:
        if self.baseline is None or self.current is None:
            return None
        return self.current - self.baseline


def _metric_items(cat_data: dict[str, Any]) -> dict[str, float | None]:
    """Metricas comparables de una categoria: las de retrieval y la tasa de cada check."""
    out: dict[str, float | None] = {}
    for key, value in cat_data.items():
        if key in ("n", "errors", "checks"):
            continue
        if isinstance(value, (int, float)) or value is None:
            out[key] = value
    for name, data in (cat_data.get("checks") or {}).items():
        out[f"check:{name}"] = data.get("rate")
    return out


def compare(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    max_regression: float = DEFAULT_MAX_REGRESSION,
) -> list[Finding]:
    if baseline["suite"]["sha256"] != current["suite"]["sha256"]:
        raise GateError(
            "el golden set no es el mismo que el del baseline: la comparacion no significa "
            "nada.\n"
            f"  baseline : {baseline['suite']['sha256'][:16]}…\n"
            f"  corrida  : {current['suite']['sha256'][:16]}…\n"
            "Si el set cambio a proposito, regenera el baseline y decilo en el commit."
        )
    if baseline.get("k") != current.get("k"):
        raise GateError(
            f"el baseline se midio con k={baseline.get('k')} y esta corrida con "
            f"k={current.get('k')}. recall@k con distinto k no es comparable."
        )

    hallazgos: list[Finding] = []
    cats_base = baseline["categories"]
    cats_cur = current["categories"]

    for cat, base_data in cats_base.items():
        cur_data = cats_cur.get(cat)
        if cur_data is None:
            hallazgos.append(Finding(
                cat, "(categoria)", None, None, "verificabilidad",
                "la categoria desaparecio de la corrida",
            ))
            continue

        base_metrics = _metric_items(base_data)
        cur_metrics = _metric_items(cur_data)

        for metric, base_val in base_metrics.items():
            cur_val = cur_metrics.get(metric)

            if base_val is None:
                if cur_val is not None:
                    hallazgos.append(Finding(
                        cat, metric, None, cur_val, "nuevo",
                        "antes no era verificable y ahora si",
                    ))
                continue

            if cur_val is None:
                hallazgos.append(Finding(
                    cat, metric, base_val, None, "verificabilidad",
                    "dejo de ser verificable — el numero no se mantuvo, desaparecio",
                ))
                continue

            delta = cur_val - base_val
            if delta < -max_regression:
                hallazgos.append(Finding(
                    cat, metric, base_val, cur_val, "regresion",
                    f"cayo {abs(delta):.3f}, mas que el maximo tolerado {max_regression:.3f}",
                ))
            elif delta > max_regression:
                hallazgos.append(Finding(
                    cat, metric, base_val, cur_val, "mejora",
                    f"subio {delta:.3f} — verificar que no sea un bug del eval",
                ))

    for cat in cats_cur:
        if cat not in cats_base:
            hallazgos.append(Finding(
                cat, "(categoria)", None, None, "nuevo", "categoria nueva, sin baseline",
            ))

    orden = {"regresion": 0, "verificabilidad": 1, "mejora": 2, "nuevo": 3}
    return sorted(hallazgos, key=lambda f: (orden[f.kind], f.category, f.metric))


def render(hallazgos: list[Finding], *, max_regression: float) -> str:
    out: list[str] = [""]
    bloquean = [f for f in hallazgos if f.blocks]

    def fmt(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.3f}"

    if not hallazgos:
        out.append(f"  ✓ sin cambios fuera de la tolerancia (±{max_regression:.3f})")
        out.append("")
        return "\n".join(out)

    for kind, titulo in (
        ("regresion", "REGRESIONES — bloquean el build"),
        ("verificabilidad", "VERIFICABILIDAD PERDIDA — bloquea el build"),
        ("mejora", "mejoras (no bloquean)"),
        ("nuevo", "nuevo (no bloquea)"),
    ):
        grupo = [f for f in hallazgos if f.kind == kind]
        if not grupo:
            continue
        out.append(f"  {titulo}")
        for f in grupo:
            out.append(
                f"    {f.category}/{f.metric}: {fmt(f.baseline)} → {fmt(f.current)}  · {f.detail}"
            )
        out.append("")

    out.append(
        f"  ✗ el gate FALLA: {len(bloquean)} hallazgo(s) bloqueante(s)"
        if bloquean
        else "  ✓ el gate pasa: ningun hallazgo bloqueante"
    )
    out.append("")
    return "\n".join(out)
