"""M2 acceptance criterion: with an invented number `grounded` is false, and with a
`forbidden_number` present that check is false too.
"""

import pytest

from groundcheck.checks import evaluate, looks_like_abstention
from groundcheck.numbers import canonicalize, contains_number, extract_codes, extract_numbers
from groundcheck.schema import Case, GoldSource, Response

CHUNK = (
    "Tabla 7.3 — Pares de apriete del cabezal.\n"
    "M20 grado 8.8: 400 ± 20 N·m\n"
    "M24 grado 8.8: 680 ± 30 N·m\n"
    "M27 grado 10.9: 950 ± 40 N·m\n"
)


def case(**kw) -> Case:
    base = dict(
        id="torque-m24",
        question="¿Torque del M24 grado 8.8?",
        category="factual_lookup",
        gold_answer="680 ± 30 N·m",
        gold_numbers=("680", "30"),
        forbidden_numbers=("950", "400"),
        gold_sources=(GoldSource(doc_id="LAM-2-MAINT", revision="D", pages=(147,)),),
    )
    base.update(kw)
    return Case(**base)


def answer(answer, *, text=CHUNK, doc="LAM-2-MAINT", page=147, rev="D", abstained=False):
    cita = {"doc_id": doc, "page": page, "revision": rev}
    if text is not None:
        cita["text"] = text
    return Response(answer=answer, citations=(cita,), abstained=abstained)


# ─────────────────────────────────────────────────────────────────────────────
# THE ACCEPTANCE CRITERION
# ─────────────────────────────────────────────────────────────────────────────
def test_an_invented_number_makes_grounded_false():
    # 725 is in no row of the cited chunk: it is invented.
    r = evaluate(case(), answer("El torque del M24 es 725 N·m."))
    assert r["grounded"].passed is False
    assert "725" in r["grounded"].evidence["unsupported"]


def test_a_present_forbidden_number_makes_the_check_false():
    # 950 is the M27 row. It appears -> it crossed rows.
    r = evaluate(case(), answer("El torque del M24 es 950 ± 40 N·m."))
    assert r["forbidden_numbers_absent"].passed is False
    assert "950" in r["forbidden_numbers_absent"].evidence["present"]


def test_the_case_that_justifies_having_both_checks():
    """A forbidden number IS in the cited chunk: `grounded` passes and `forbidden` fails.

    This is exactly the split-table bug. Groundedness alone lets it through — the 950 is
    literally in the table — which is why `forbidden_numbers` is not redundant: it names
    the failure the other check cannot see.
    """
    r = evaluate(case(), answer("El torque del M24 es 950 ± 40 N·m."))
    assert r["grounded"].passed is True            # 950 y 40 estan en el chunk
    assert r["forbidden_numbers_absent"].passed is False
    assert r["gold_numbers_present"].passed is False   # falta el 680


def test_a_correct_answer_passes_everything_verifiable():
    r = evaluate(case(), answer("El torque de apriete del M24 grado 8.8 es 680 ± 30 N·m."))
    assert r["gold_numbers_present"].passed is True
    assert r["forbidden_numbers_absent"].passed is True
    assert r["grounded"].passed is True
    assert r["citation_hits_gold"].passed is True
    assert r["abstention_correct"].passed is True
    assert r["revision_current"].passed is True


# ─────────────────────────────────────────────────────────────────────────────
# `None` is not a failure — the module's central distinction
# ─────────────────────────────────────────────────────────────────────────────
def test_without_citation_text_grounded_is_None_not_false():
    r = evaluate(case(), answer("El torque es 680 ± 30 N·m.", text=None))
    assert r["grounded"].passed is None
    assert "does not expose" in r["grounded"].detail
    # The checks that do not depend on the chunk text keep working.
    assert r["gold_numbers_present"].passed is True
    assert r["citation_hits_gold"].passed is True


def test_an_unreported_revision_is_None():
    r = evaluate(case(), answer("680 ± 30 N·m", rev=None))
    assert r["revision_current"].passed is None


def test_a_case_without_gold_numbers_leaves_the_check_None():
    r = evaluate(case(gold_numbers=(), forbidden_numbers=()), answer("Se aprieta en cruz."))
    assert r["gold_numbers_present"].passed is None
    assert r["forbidden_numbers_absent"].passed is None


def test_with_no_response_due_to_error_everything_stays_None():
    r = evaluate(case(), None)
    assert all(res.passed is None for res in r.values())
    assert all("did not answer" in res.detail for res in r.values())


# ─────────────────────────────────────────────────────────────────────────────
# Negative control: the most important metric in the set
# ─────────────────────────────────────────────────────────────────────────────
NEGATIVE = Case(
    id="torque-m30-ausente",
    question="¿Torque del M30?",
    category="negative_control",
    must_abstain=True,
)


def test_a_negative_control_that_abstains_passes():
    r = evaluate(NEGATIVE, Response(answer=None, abstained=True))
    assert r["abstention_correct"].passed is True


def test_a_negative_control_that_answers_is_a_hallucination():
    r = evaluate(NEGATIVE, answer("El torque del M30 es 1200 N·m."))
    assert r["abstention_correct"].passed is False
    assert "HALLUCINATED" in r["abstention_correct"].detail


def test_abstention_detected_by_phrase_even_when_undeclared():
    # The system did not set the flag but the answer is a refusal in text.
    r = evaluate(NEGATIVE, Response(answer="No encontré ese dato en la documentación."))
    assert r["abstention_correct"].passed is True
    assert r["abstention_correct"].evidence["declared"] is False
    assert r["abstention_correct"].evidence["by_phrase"] is True


def test_abstaining_on_a_case_with_an_answer_is_a_failure():
    r = evaluate(case(), Response(answer=None, abstained=True))
    assert r["abstention_correct"].passed is False
    assert r["gold_numbers_present"].passed is False
    # Groundedness is not held against something that said nothing.
    assert r["grounded"].passed is None


@pytest.mark.parametrize(
    "texto,esperado",
    [
        (None, True),
        ("", True),
        ("   ", True),
        ("No encontré ese dato.", True),
        ("No figura en la revisión D.", True),
        ("I could not find that value.", True),
        ("El torque es 680 N·m.", False),
    ],
)
def test_abstention_detection_by_phrase_list(texto, esperado):
    assert looks_like_abstention(texto) is esperado


# ─────────────────────────────────────────────────────────────────────────────
# The alphanumeric-code trap (rule 1 of `numbers.py`)
# ─────────────────────────────────────────────────────────────────────────────
def test_a_code_does_not_contribute_its_number():
    assert extract_numbers("La alarma E-114 del perno M24") == []
    assert extract_codes("La alarma E-114 del perno M24") == ["E-114", "M24"]


def test_a_correct_code_answer_does_not_fail_groundedness():
    """The false negative rule 1 prevents.

    Without it, "E-114" would contribute the number 114, which never appears loose in the
    chunk, and the CORRECT answer would return `grounded: false`. That sends you to fix a
    healthy system.
    """
    c = Case(
        id="alarma",
        question="¿Qué es la alarma E-114?",
        category="alfanumerico_exacto",
        gold_sources=(GoldSource(doc_id="LAM-2-ALARMS", revision="B", pages=(12,)),),
    )
    chunk = "E-114 — Sobretemperatura del cojinete de output. Umbral 95 °C."
    r = evaluate(c, answer("La alarma E-114 es sobretemperatura del cojinete de output.",
                              text=chunk, doc="LAM-2-ALARMS", page=12, rev="B"))
    assert r["grounded"].passed is True


def test_an_invented_code_does_fail_groundedness():
    c = Case(id="a", question="q", category="alfanumerico_exacto",
             gold_sources=(GoldSource(doc_id="D", pages=(1,)),))
    r = evaluate(c, answer("Ver la alarma E-999.", text="E-114 — Sobretemperatura.",
                              doc="D", page=1, rev=None))
    assert r["grounded"].passed is False
    assert "E-999" in r["grounded"].evidence["unsupported"]


# ─────────────────────────────────────────────────────────────────────────────
# Number normalisation
# ─────────────────────────────────────────────────────────────────────────────
def test_a_substring_is_not_mistaken_for_a_number():
    # "30" is NOT in "1300": comparing raw substrings would declare grounded a number
    # that was never there.
    assert contains_number("el valor es 1300", "30") is False
    assert contains_number("el valor es 30", "30") is True


@pytest.mark.parametrize(
    "crudo,canonico",
    [
        ("680", "680"),
        ("680.0", "680"),      # los ceros de cola no crean un numero distinto
        ("68,5", "68.5"),
        ("1.200", "1200"),     # separador de miles (convencion documentada)
        ("1,200", "1200"),
        ("1.200,50", "1200.5"),  # ambos separadores: el ultimo es decimal
        ("1,200.50", "1200.5"),
    ],
)
def test_canonicalisation(crudo, canonico):
    assert canonicalize(crudo) == canonico


def test_a_gold_number_in_another_format_still_counts():
    # The set says "680" and the answer writes "680.0": it is the same number.
    r = evaluate(case(), answer("El torque es 680.0 ± 30 N·m."))
    assert r["gold_numbers_present"].passed is True


# ─────────────────────────────────────────────────────────────────────────────
# Citations and revisions
# ─────────────────────────────────────────────────────────────────────────────
def test_citing_the_wrong_page_fails():
    r = evaluate(case(), answer("680 ± 30 N·m", page=200))
    assert r["citation_hits_gold"].passed is False


def test_a_superseded_revision_fails():
    r = evaluate(case(), answer("680 ± 30 N·m", rev="B"))
    assert r["revision_current"].passed is False
    assert "superseded" in r["revision_current"].detail
    assert r["revision_current"].evidence == {"current": ["D"], "cited": ["B"]}


def test_citing_nothing_fails_the_citation_check():
    r = evaluate(case(), Response(answer="680 ± 30 N·m", citations=()))
    assert r["citation_hits_gold"].passed is False
    assert r["citation_hits_gold"].detail == "it cited nothing"


# ─────────────────────────────────────────────────────────────────────────────
# Rules 2 and 3 of `numbers.py` — the three defects found while labelling M3
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "token",
    ["9150-00-292-9689", "1.9.4", "14.2.29", "MIL-PRF-14107", "E-114", "M24", "QS-1", "12/07/2024"],
)
def test_identifiers_are_not_split_into_numbers(token):
    assert extract_numbers(token) == []
    assert extract_codes(token) == [token.upper()]


@pytest.mark.parametrize("token", ["720", "30", "8.8", "68,5", "1.200", "1.200,50", "1.200.000"])
def test_numbers_are_still_numbers(token):
    assert [t.raw for t in extract_numbers(token)] == [token]
    assert extract_codes(token) == []


def test_a_wrong_version_does_not_pass_groundedness():
    """The false positive rule 2 prevents — the worst of the three defects.

    Without it, `1.9.4` was split into "1.9" and "4". A system answering "Leaflet 1.9.5"
    passed `grounded` because the chunk carried a 1.9 and some 5 elsewhere: it published as
    grounded something that was not.
    """
    c = Case(id="ver", question="¿Qué versión de Leaflet?", category="alfanumerico_exacto",
             gold_sources=(GoldSource(doc_id="TP", pages=(3,)),))
    chunk = "| Mapas | Leaflet 1.9.4 |\n| UI | React 18 |\n| Pagos | 5 métodos |"

    correcta = evaluate(c, answer("Usa Leaflet 1.9.4.", text=chunk, doc="TP", page=3, rev=None))
    assert correcta["grounded"].passed is True

    equivocada = evaluate(c, answer("Usa Leaflet 1.9.5.", text=chunk, doc="TP", page=3, rev=None))
    assert equivocada["grounded"].passed is False
    assert "1.9.5" in equivocada["grounded"].evidence["unsupported"]


def test_an_invented_nsn_does_not_pass_groundedness():
    """Before, an NSN was neither number nor code: it was invisible to `grounded`."""
    c = Case(id="nsn", question="¿NSN del aceite LAW?", category="alfanumerico_exacto",
             gold_sources=(GoldSource(doc_id="TM", pages=(126,)),))
    chunk = "| 9 | C | 9150-00-292-9689 | LUBRICATING OIL, WEAPONS LOW TEMPERATURE (LAW) |"

    ok = evaluate(c, answer("El NSN es 9150-00-292-9689.", text=chunk, doc="TM", page=126, rev=None))
    assert ok["grounded"].passed is True

    mal = evaluate(c, answer("El NSN es 9150-00-292-9999.", text=chunk, doc="TM", page=126, rev=None))
    assert mal["grounded"].passed is False


# ─────────────────────────────────────────────────────────────────────────────
# Rule 4 and the question exemption — the two false negatives M4 found
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("1) Notificar. 2) Abrir QS-1.", []),
        ("1. Primero  2. Segundo", []),
        ("| (3) NATIONAL STOCK NUMBER |", []),
        ("3 pasadas en cruz", ["3"]),          # a number that asserts DOES count
        ("720 +/- 30 N.m", ["720", "30"]),
    ],
)
def test_list_markers_are_not_numbers(texto, esperado):
    """Rule 4: a system that numbers its steps must not fail groundedness for numbering."""
    assert [t.raw for t in extract_numbers(texto)] == esperado


def test_a_numbered_procedure_is_grounded():
    c = Case(id="loto", question="¿Cuál es el procedimiento LOTO?", category="procedimental",
             gold_sources=(GoldSource(doc_id="D", pages=(1,)),))
    chunk = "Notificar a produccion y detener la linea.\nAbrir el seccionador QS-1."
    r = evaluate(c, answer("1) Notificar a produccion y detener la linea. 2) Abrir el "
                              "seccionador QS-1.", text=chunk, doc="D", page=1, rev=None))
    assert r["grounded"].passed is True


def test_a_number_from_the_question_is_exempt():
    """Repeating the question is not hallucinating.

    The question carries "15 mm"; the table speaks of "up to 20" and "over 20". Without the
    exemption, the correct answer would fail for citing the thickness the user asked about.
    """
    c = Case(
        id="delgado",
        question="¿Hay que precalentar el A516 Gr.70 de 15 mm de espesor?",
        category="factual_lookup",
        gold_sources=(GoldSource(doc_id="D", pages=(1,)),),
    )
    chunk = "| A516 Gr.70 | hasta 20 | ninguno |\n| A106 Gr.B | cualquiera | 80 |"
    r = evaluate(c, answer("El A516 Gr.70 de 15 mm no requiere precalentamiento.",
                              text=chunk, doc="D", page=1, rev=None))
    assert r["grounded"].passed is True
    assert "15" in r["grounded"].evidence["exempt_because_in_question"]


def test_the_exemption_does_not_let_an_invented_number_through():
    c = Case(
        id="delgado",
        question="¿Hay que precalentar el A516 Gr.70 de 15 mm?",
        category="factual_lookup",
        gold_sources=(GoldSource(doc_id="D", pages=(1,)),),
    )
    chunk = "| A516 Gr.70 | hasta 20 | ninguno |"
    # The 15 is exempt; the 240 is not, and it is not in the chunk.
    r = evaluate(c, answer("El A516 Gr.70 de 15 mm requiere 240 C.",
                              text=chunk, doc="D", page=1, rev=None))
    assert r["grounded"].passed is False
    assert r["grounded"].evidence["unsupported"] == ["240"]


def test_the_negative_control_does_not_escape_through_the_exemption():
    """The question asks about M30: the `M30` is exempt, but hallucination is handled by
    `check_abstention`, which is its own check. The division of labour matters."""
    c = Case(id="m30", question="¿Cuál es el par de apriete del perno M30 del cabezal?",
             category="negative_control", must_abstain=True,
             gold_sources=(GoldSource(doc_id="D", pages=(1,)),))
    chunk = "| M24 cabezal | 8.8 | 720 +/- 30 |\n| M16 tapa | 8.8 | 190 +/- 10 |"
    r = evaluate(c, answer("El par del M30 es 720 +/- 30 N.m.", text=chunk, doc="D",
                              page=1, rev=None))
    assert r["grounded"].passed is True            # el 720 esta literal en la tabla
    assert r["abstention_correct"].passed is False  # y acá se lo atrapa


# ─────────────────────────────────────────────────────────────────────────────
# forbidden_codes — the format gap M3 left noted
# ─────────────────────────────────────────────────────────────────────────────
ALARMAS = (
    "| E-114 | Sobretemperatura de bobina        | Parar y purgar refrigerante |\n"
    "| E-115 | Perdida de caudal de refrigerante | Verificar bomba P-3         |\n"
    "| E-141 | Fallo de aislamiento              | Bloquear equipo             |\n"
)


def alarm_case(**kw) -> Case:
    base = dict(
        id="alarma-e114",
        question="¿Qué significa la alarma E-114?",
        category="alfanumerico_exacto",
        gold_answer="Sobretemperatura de bobina",
        forbidden_codes=("E-115", "E-141"),
        gold_sources=(GoldSource(doc_id="LAM", pages=(1,)),),
    )
    base.update(kw)
    return Case(**base)


def test_answering_the_neighbouring_alarm_is_caught_by_forbidden_codes():
    """The trap `forbidden_numbers` CANNOT see.

    The "115" in E-115 lives inside an identifier and is never extracted as a number, so
    without this check the wrong answer passed everything: it cites correctly, it is
    grounded (the table carries all three rows) and it holds no forbidden number.
    """
    r = evaluate(alarm_case(), answer(
        "La alarma E-115 indica perdida de caudal de refrigerante.",
        text=ALARMAS, doc="LAM", page=1, rev=None))
    assert r["forbidden_codes_absent"].passed is False
    assert "E-115" in r["forbidden_codes_absent"].evidence["present"]
    # And you can see why it was needed: the other checks let it through.
    assert r["grounded"].passed is True
    assert r["citation_hits_gold"].passed is True


def test_the_correct_answer_passes_forbidden_codes():
    r = evaluate(alarm_case(), answer(
        "La alarma E-114 indica sobretemperatura de bobina.",
        text=ALARMAS, doc="LAM", page=1, rev=None))
    assert r["forbidden_codes_absent"].passed is True


def test_without_forbidden_codes_the_check_is_None():
    r = evaluate(alarm_case(forbidden_codes=()), answer(
        "La alarma E-114 indica sobretemperatura.", text=ALARMAS, doc="LAM", page=1, rev=None))
    assert r["forbidden_codes_absent"].passed is None


def test_forbidden_codes_compare_case_insensitively():
    r = evaluate(alarm_case(forbidden_codes=("e-115",)), answer(
        "Ver E-115.", text=ALARMAS, doc="LAM", page=1, rev=None))
    assert r["forbidden_codes_absent"].passed is False


def test_a_forbidden_code_present_in_the_gold_answer_is_an_error(tmp_path):
    """It would be a trap against the correct answer: the case would always fail."""
    from groundcheck.suite import SuiteError, load_suite

    body = (
        "cases:\n  - id: x\n    question: q\n    category: alfanumerico_exacto\n"
        "    gold_answer: 'Ver la alarma E-114'\n    forbidden_codes: ['E-114']\n"
    )
    p = tmp_path / "s.yaml"
    p.write_text(body, "utf-8")
    with pytest.raises(SuiteError, match="is in both"):
        load_suite(p)


# ─────────────────────────────────────────────────────────────────────────────
# Rule 4b — citation markers (the false negative the real run found)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("720 +/- 30 N.m [1]", ["720", "30"]),
        ("Leaflet 1.9.4 [5]", []),
        ("Ver [1,2] y [3-4]", []),
        ("El valor es 80 [3]", ["80"]),
        ("La tabla 1 dice 720", ["1", "720"]),   # un 1 suelto SÍ es un dato
    ],
)
def test_citation_markers_are_not_data(texto, esperado):
    assert [t.raw for t in extract_numbers(texto)] == esperado


def test_citing_properly_cannot_fail_groundedness():
    """The false negative rule 4b prevents, measured against the real shopfloor.

    shopfloor cites with `[n]`. Without this rule its groundedness read 0.18 with CORRECT
    answers: the harness was punishing the system for citing, which is exactly the
    behaviour it rewards in every other check.
    """
    c = Case(id="t", question="¿Torque del M24 grado 8.8?", category="factual_lookup",
             gold_numbers=("720", "30"),
             gold_sources=(GoldSource(doc_id="LAM", revision="F", pages=(1,)),))
    chunk = "| M24 cabezal | 8.8 | 720 +/- 30 | cruzada, 3 pasadas |"
    r = evaluate(c, answer("720 +/- 30 N.m [1]", text=chunk, doc="LAM", page=1, rev="F"))
    assert r["grounded"].passed is True
    assert r["gold_numbers_present"].passed is True
