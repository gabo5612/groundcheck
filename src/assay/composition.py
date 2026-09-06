"""Validacion de la composicion de un golden set.

La composicion importa mas que la cantidad (§3 del spec). Un set de 50 preguntas con 2
controles negativos mide otra cosa que la que dice medir, y eso **no se ve leyendo el
archivo**: hay que contar. Por eso es un check y no una convencion.

Nota de procedencia: el contrato se despacho a `crew`, pero el guard de archivos aborto
la corrida porque Claude edito `tests/test_checks.py` en paralelo — el whitelist no
distingue las ediciones del obrero de las del arquitecto. Leccion: no tocar el repo
mientras crew despacha. Esta version la escribio Claude contra los mismos tests.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CompositionIssue:
    category: str
    kind: str          # 'ausente' · 'bajo' · 'alto' · 'desconocida'
    n: int
    total: int
    actual: float
    objetivo: float
    faltan: int
    blocks: bool


def composition_report(
    conteo: dict[str, int],
    objetivo: dict[str, float],
    tolerancia: float,
) -> list[CompositionIssue]:
    """Compara la composicion real contra la objetivo.

    Quedarse CORTO en una categoria bloquea; pasarse no. La asimetria es deliberada: si
    `negative_control` baja del 20%, el set deja de medir alucinacion y todos los numeros
    que publique valen menos. Tener preguntas de mas en otra categoria solo desbalancea.
    """
    total = sum(conteo.values())
    if total == 0:
        return []

    issues: list[CompositionIssue] = []

    for categoria, n in conteo.items():
        if categoria not in objetivo:
            issues.append(
                CompositionIssue(categoria, "desconocida", n, total, n / total, 0.0, 0, True)
            )

    for categoria, esperado in objetivo.items():
        n = conteo.get(categoria, 0)
        actual = n / total
        faltan = max(0, math.ceil(esperado * total) - n)

        if n == 0:
            issues.append(
                CompositionIssue(categoria, "ausente", 0, total, 0.0, esperado, faltan, True)
            )
        elif actual < esperado - tolerancia:
            issues.append(
                CompositionIssue(categoria, "bajo", n, total, actual, esperado, faltan, True)
            )
        elif actual > esperado + tolerancia:
            issues.append(
                CompositionIssue(categoria, "alto", n, total, actual, esperado, 0, False)
            )

    return sorted(issues, key=lambda i: (not i.blocks, i.category))
