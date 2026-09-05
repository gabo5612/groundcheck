"""Clasificacion de transiciones de check entre dos corridas.

`gate` responde "recall@5 cayo 0.25". Este modulo responde **que casos se dieron vuelta**,
que es lo que se necesita para arreglar algo: una categoria no se mueve sola, se mueve
porque tres preguntas concretas pasaron de pasar a fallar.

Nota de procedencia: el contrato de este modulo se despacho a los modelos locales via
`crew`. El 7B fallo 3 intentos (14/20 tests) y el 14B llego a 19/20, fallando solo la
transicion `False -> None` — el clasico `if not antes` en vez de `if antes is not None`.
crew revirtio el trabajo y escalo, y esta version la escribio Claude. El bug del 14B es
justo el que un test parametrizado atrapa y una revision por lectura no.
"""

from __future__ import annotations

from dataclasses import dataclass

# Prioridad de lectura: lo que rompio primero, lo que es ruido al final.
KIND_ORDER = {
    "rompio": 0,
    "se_apago": 1,
    "desaparecido": 2,
    "se_prendio": 3,
    "arreglo": 4,
    "nuevo": 5,
}


@dataclass(frozen=True)
class Flip:
    case_id: str
    check: str
    antes: bool | None
    despues: bool | None
    kind: str


def _kind(antes: bool | None, despues: bool | None) -> str:
    # `is None` y no falsy: False es un valor, no una ausencia. Confundirlos hace que
    # perder la verificabilidad de un check que fallaba se lea como una mejora.
    if antes is None:
        return "se_prendio"
    if despues is None:
        return "se_apago"
    return "arreglo" if despues else "rompio"


def classify_flips(
    antes: dict[str, dict[str, bool | None]],
    despues: dict[str, dict[str, bool | None]],
) -> list[Flip]:
    """Transiciones de check entre dos corridas, ordenadas por gravedad.

    Un caso que aparece o desaparece es **un** hallazgo, no seis: si no, agregar una
    pregunta al golden set inunda el diff y esconde las regresiones reales.
    """
    flips: list[Flip] = []
    posicion: dict[tuple[str, str], int] = {}

    for case_id, checks_despues in despues.items():
        if case_id not in antes:
            flips.append(Flip(case_id, "(caso)", None, None, "nuevo"))
            continue

        checks_antes = antes[case_id]
        # Orden de lectura: los checks de `despues` primero, y despues los que solo
        # existian antes (los que se apagaron del todo).
        nombres = list(checks_despues) + [c for c in checks_antes if c not in checks_despues]
        for i, nombre in enumerate(nombres):
            a = checks_antes.get(nombre)
            d = checks_despues.get(nombre)
            if a == d:
                continue
            posicion[(case_id, nombre)] = i
            flips.append(Flip(case_id, nombre, a, d, _kind(a, d)))

    for case_id in antes:
        if case_id not in despues:
            flips.append(Flip(case_id, "(caso)", None, None, "desaparecido"))

    return sorted(
        flips,
        key=lambda f: (
            KIND_ORDER[f.kind],
            f.case_id,
            posicion.get((f.case_id, f.check), 0),
        ),
    )
