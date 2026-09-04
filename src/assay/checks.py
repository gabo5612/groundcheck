"""Checks deterministas de generacion.

Todos son operaciones de conjuntos y comparaciones de strings normalizados. Ningun modelo
participa: la regla de diseno de §4 del contexto es que lo determinista bloquea el CI y lo
difuso solo se reporta.

Tres estados por check, y la distincion entre los dos ultimos es el corazon del modulo:

- `True`  — se verifico y pasa
- `False` — se verifico y **falla**
- `None`  — **no se pudo verificar** (falta el insumo: el sistema no expuso el texto del
            chunk citado, o el caso no define numeros de oro)

`None` nunca se cuenta como fallo ni como exito. Un harness que convierte "no pude
verificar" en "fallo" empuja a arreglar cosas que no estaban rotas; uno que lo convierte
en "pasa" publica un numero que no midio nada. Por eso el reporte los muestra aparte.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .metrics import RetrievedItem, matches
from .numbers import contains_number, extract_codes, extract_numbers
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


# ── frases de abstencion ─────────────────────────────────────────────────────
# Lista de frases, no un modelo. §8 del contexto lo dice explicito: empezar con lista y
# revision manual de los desacuerdos, sin meter un modelo a decidir si otro modelo se
# abstuvo. La lista es visible y auditable; un clasificador seria una caja negra dentro
# del propio verificador.
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
    """Texto de los chunks citados, si el sistema lo expone."""
    out = []
    for c in response.citations:
        text = c.get("text") or c.get("snippet") or c.get("content")
        if isinstance(text, str) and text.strip():
            out.append(text)
    return out


# ── los checks ───────────────────────────────────────────────────────────────
def check_gold_numbers(case: Case, response: Response) -> CheckResult:
    """Cada `gold_number` aparece literal en la respuesta."""
    if not case.gold_numbers:
        return CheckResult("gold_numbers_present", None, "el caso no define numeros de oro")
    if response.abstained:
        return CheckResult(
            "gold_numbers_present", False, "se abstuvo en un caso que si tiene respuesta"
        )
    faltantes = [n for n in case.gold_numbers if not contains_number(response.answer, n)]
    return CheckResult(
        "gold_numbers_present",
        not faltantes,
        "todos presentes" if not faltantes else f"faltan {faltantes}",
        {"esperados": list(case.gold_numbers), "faltantes": faltantes},
    )


def check_forbidden_numbers(case: Case, response: Response) -> CheckResult:
    """Ningun `forbidden_number` aparece en la respuesta.

    Es el check que atrapa el bug de la tabla partida: si la respuesta trae 950 cuando
    debia traer 680, no es "una respuesta algo distinta" — es haber cruzado filas.
    """
    if not case.forbidden_numbers:
        return CheckResult("forbidden_numbers_absent", None, "el caso no define prohibidos")
    presentes = [n for n in case.forbidden_numbers if contains_number(response.answer, n)]
    return CheckResult(
        "forbidden_numbers_absent",
        not presentes,
        "ninguno presente" if not presentes else f"aparecen {presentes} — cruzo filas",
        {"prohibidos": list(case.forbidden_numbers), "presentes": presentes},
    )


def check_grounded(case: Case, response: Response) -> CheckResult:
    """Cada numero y codigo de la respuesta esta literal en algun chunk citado.

    Sin el texto de los chunks no se puede verificar, y en ese caso da `None`: decir
    "no fundamentado" porque el sistema no expone sus chunks seria culparlo de algo que
    no se midio.

    **Los numeros y codigos que ya estaban en la pregunta estan exentos.** Groundedness
    pregunta si el sistema *introdujo* un dato sin respaldo; un dato que escribio el
    usuario no lo introdujo el sistema. Sin esta exencion, contestar "el A516 de 15 mm no
    requiere precalentamiento" falla porque el "15" no esta en la tabla — y repetir el
    enunciado no es alucinar. (Encontrado al llenar el reporte de M4.)

    El control negativo no se escapa por esta puerta: si preguntan por el perno M30, el
    `M30` queda exento pero cualquier torque que invente sigue teniendo que estar en el
    chunk, y de la abstencion se ocupa `check_abstention`, que es su check.
    """
    if response.abstained:
        return CheckResult("grounded", None, "se abstuvo: no hay nada que fundamentar")

    textos = _citation_texts(response)
    if not textos:
        return CheckResult(
            "grounded",
            None,
            "las citas no traen texto — el sistema no expone el contenido del chunk",
            {"citas": len(response.citations)},
        )

    corpus = "\n".join(textos)
    numeros = extract_numbers(response.answer)
    codigos = extract_codes(response.answer)

    # Exencion por enunciado: lo que ya venia en la pregunta no lo introdujo el sistema.
    num_pregunta = {t.canonical for t in extract_numbers(case.question)}
    cod_pregunta = set(extract_codes(case.question))

    num_huerfanos = [
        t.raw
        for t in numeros
        if t.canonical not in num_pregunta and not contains_number(corpus, t.raw)
    ]
    cod_corpus = set(extract_codes(corpus))
    cod_huerfanos = [c for c in codigos if c not in cod_pregunta and c not in cod_corpus]

    huerfanos = num_huerfanos + cod_huerfanos
    if not numeros and not codigos:
        return CheckResult(
            "grounded", None, "la respuesta no trae numeros ni codigos que verificar"
        )
    return CheckResult(
        "grounded",
        not huerfanos,
        "todo fundamentado" if not huerfanos else f"inventado(s): {huerfanos}",
        {
            "numeros_en_respuesta": [t.raw for t in numeros],
            "codigos_en_respuesta": codigos,
            "exentos_por_venir_en_la_pregunta": sorted(num_pregunta | cod_pregunta),
            "sin_respaldo": huerfanos,
        },
    )


def check_citation_hits_gold(case: Case, response: Response) -> CheckResult:
    """Alguna cita apunta al documento/pagina de oro."""
    objetivos = case.targets()
    if not objetivos:
        return CheckResult("citation_hits_gold", None, "el caso no define fuente de oro")
    if not response.citations:
        return CheckResult("citation_hits_gold", False, "no cito nada")

    items = [RetrievedItem.from_raw(c, i) for i, c in enumerate(response.citations, start=1)]
    aciertos = [
        {"doc_id": it.doc_id, "page": it.page}
        for it in items
        if any(matches(it, doc, pages) for doc, pages in objetivos)
    ]
    return CheckResult(
        "citation_hits_gold",
        bool(aciertos),
        "cita correcta" if aciertos else "ninguna cita apunta a la fuente de oro",
        {"objetivos": [{"doc_id": d, "pages": list(p)} for d, p in objetivos], "aciertos": aciertos},
    )


def check_abstention(case: Case, response: Response) -> CheckResult:
    """En los controles negativos, se abstuvo. En el resto, contesto.

    Es la metrica mas importante del set: sin ella, un sistema que siempre responde con
    seguridad puntua perfecto.
    """
    declarada = response.abstained
    por_frase = looks_like_abstention(response.answer)
    abstuvo = declarada or por_frase

    if case.must_abstain:
        return CheckResult(
            "abstention_correct",
            abstuvo,
            "se abstuvo, correcto" if abstuvo else "ALUCINO: contesto una pregunta sin respuesta",
            {"declarada": declarada, "por_frase": por_frase, "esperado": "abstenerse"},
        )
    return CheckResult(
        "abstention_correct",
        not abstuvo,
        "contesto, correcto" if not abstuvo else "se abstuvo en un caso que si tiene respuesta",
        {"declarada": declarada, "por_frase": por_frase, "esperado": "responder"},
    )


def check_revision_current(case: Case, response: Response) -> CheckResult:
    """Cito la revision vigente y no una supersedida."""
    revisiones_oro = {s.revision for s in case.gold_sources if s.revision}
    if not revisiones_oro:
        return CheckResult("revision_current", None, "el caso no fija revision de oro")

    citadas = {str(c["revision"]) for c in response.citations if c.get("revision") is not None}
    if not citadas:
        return CheckResult(
            "revision_current", None, "las citas no reportan revision — no se puede verificar"
        )

    obsoletas = citadas - revisiones_oro
    return CheckResult(
        "revision_current",
        not obsoletas,
        "revision vigente" if not obsoletas else f"cito revision supersedida: {sorted(obsoletas)}",
        {"vigentes": sorted(revisiones_oro), "citadas": sorted(citadas)},
    )


CHECKS = (
    check_gold_numbers,
    check_forbidden_numbers,
    check_grounded,
    check_citation_hits_gold,
    check_abstention,
    check_revision_current,
)


def evaluate(case: Case, response: Response | None) -> dict[str, CheckResult]:
    """Todos los checks sobre un caso. Sin respuesta, todos quedan sin verificar."""
    if response is None:
        return {
            fn(case, Response(answer=None)).name: CheckResult(
                fn(case, Response(answer=None)).name, None, "el sistema no respondio (error)"
            )
            for fn in CHECKS
        }
    resultados = [fn(case, response) for fn in CHECKS]
    return {r.name: r for r in resultados}
