"""Criterio de aceptacion de M2: con un numero inventado `grounded` da falso, y con un
`forbidden_number` presente el check tambien da falso.
"""

import pytest

from assay.checks import evaluate, looks_like_abstention
from assay.numbers import canonicalize, contains_number, extract_codes, extract_numbers
from assay.schema import Case, GoldSource, Response

CHUNK = (
    "Tabla 7.3 — Pares de apriete del cabezal.\n"
    "M20 grado 8.8: 400 ± 20 N·m\n"
    "M24 grado 8.8: 680 ± 30 N·m\n"
    "M27 grado 10.9: 950 ± 40 N·m\n"
)


def caso(**kw) -> Case:
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


def respuesta(answer, *, text=CHUNK, doc="LAM-2-MAINT", page=147, rev="D", abstained=False):
    cita = {"doc_id": doc, "page": page, "revision": rev}
    if text is not None:
        cita["text"] = text
    return Response(answer=answer, citations=(cita,), abstained=abstained)


# ─────────────────────────────────────────────────────────────────────────────
# EL CRITERIO DE ACEPTACION
# ─────────────────────────────────────────────────────────────────────────────
def test_numero_inventado_da_grounded_falso():
    # 725 no esta en ninguna fila del chunk citado: es inventado.
    r = evaluate(caso(), respuesta("El torque del M24 es 725 N·m."))
    assert r["grounded"].passed is False
    assert "725" in r["grounded"].evidence["sin_respaldo"]


def test_numero_prohibido_presente_da_el_check_falso():
    # 950 es la fila del M27. Aparece -> cruzo filas.
    r = evaluate(caso(), respuesta("El torque del M24 es 950 ± 40 N·m."))
    assert r["forbidden_numbers_absent"].passed is False
    assert "950" in r["forbidden_numbers_absent"].evidence["presentes"]


def test_el_caso_que_justifica_tener_los_dos_checks():
    """Un numero prohibido SI esta en el chunk citado: `grounded` pasa y `forbidden` falla.

    Es exactamente el bug de la tabla partida. Groundedness sola lo deja pasar —el 950
    esta literal en la tabla— y por eso `forbidden_numbers` no es redundante: nombra la
    falla que el otro check no puede ver.
    """
    r = evaluate(caso(), respuesta("El torque del M24 es 950 ± 40 N·m."))
    assert r["grounded"].passed is True            # 950 y 40 estan en el chunk
    assert r["forbidden_numbers_absent"].passed is False
    assert r["gold_numbers_present"].passed is False   # falta el 680


def test_respuesta_correcta_pasa_todo_lo_verificable():
    r = evaluate(caso(), respuesta("El torque de apriete del M24 grado 8.8 es 680 ± 30 N·m."))
    assert r["gold_numbers_present"].passed is True
    assert r["forbidden_numbers_absent"].passed is True
    assert r["grounded"].passed is True
    assert r["citation_hits_gold"].passed is True
    assert r["abstention_correct"].passed is True
    assert r["revision_current"].passed is True


# ─────────────────────────────────────────────────────────────────────────────
# `None` no es fallo — la distincion central del modulo
# ─────────────────────────────────────────────────────────────────────────────
def test_sin_texto_de_cita_grounded_es_None_no_falso():
    r = evaluate(caso(), respuesta("El torque es 680 ± 30 N·m.", text=None))
    assert r["grounded"].passed is None
    assert "no expone" in r["grounded"].detail
    # Los checks que no dependen del texto del chunk siguen funcionando.
    assert r["gold_numbers_present"].passed is True
    assert r["citation_hits_gold"].passed is True


def test_revision_no_reportada_es_None():
    r = evaluate(caso(), respuesta("680 ± 30 N·m", rev=None))
    assert r["revision_current"].passed is None


def test_caso_sin_numeros_de_oro_deja_el_check_en_None():
    r = evaluate(caso(gold_numbers=(), forbidden_numbers=()), respuesta("Se aprieta en cruz."))
    assert r["gold_numbers_present"].passed is None
    assert r["forbidden_numbers_absent"].passed is None


def test_sin_respuesta_por_error_todo_queda_en_None():
    r = evaluate(caso(), None)
    assert all(res.passed is None for res in r.values())
    assert all("no respondio" in res.detail for res in r.values())


# ─────────────────────────────────────────────────────────────────────────────
# Control negativo: la metrica mas importante del set
# ─────────────────────────────────────────────────────────────────────────────
NEGATIVO = Case(
    id="torque-m30-ausente",
    question="¿Torque del M30?",
    category="negative_control",
    must_abstain=True,
)


def test_control_negativo_que_se_abstiene_pasa():
    r = evaluate(NEGATIVO, Response(answer=None, abstained=True))
    assert r["abstention_correct"].passed is True


def test_control_negativo_que_contesta_es_alucinacion():
    r = evaluate(NEGATIVO, respuesta("El torque del M30 es 1200 N·m."))
    assert r["abstention_correct"].passed is False
    assert "ALUCINO" in r["abstention_correct"].detail


def test_abstencion_detectada_por_frase_aunque_no_la_declare():
    # El sistema no puso el flag pero la respuesta es un rechazo en texto.
    r = evaluate(NEGATIVO, Response(answer="No encontré ese dato en la documentación."))
    assert r["abstention_correct"].passed is True
    assert r["abstention_correct"].evidence["declarada"] is False
    assert r["abstention_correct"].evidence["por_frase"] is True


def test_abstenerse_en_un_caso_con_respuesta_es_fallo():
    r = evaluate(caso(), Response(answer=None, abstained=True))
    assert r["abstention_correct"].passed is False
    assert r["gold_numbers_present"].passed is False
    # No se le reprocha groundedness a quien no dijo nada.
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
def test_deteccion_de_abstencion_por_lista_de_frases(texto, esperado):
    assert looks_like_abstention(texto) is esperado


# ─────────────────────────────────────────────────────────────────────────────
# La trampa de los codigos alfanumericos (regla 1 de `numbers.py`)
# ─────────────────────────────────────────────────────────────────────────────
def test_un_codigo_no_aporta_su_numero():
    assert extract_numbers("La alarma E-114 del perno M24") == []
    assert extract_codes("La alarma E-114 del perno M24") == ["E-114", "M24"]


def test_respuesta_con_codigo_correcto_no_falla_groundedness():
    """El falso negativo que la regla 1 evita.

    Sin ella, "E-114" aportaria el numero 114, que no aparece suelto en el chunk, y la
    respuesta CORRECTA daria `grounded: false`. Eso te manda a arreglar un sistema sano.
    """
    c = Case(
        id="alarma",
        question="¿Qué es la alarma E-114?",
        category="alfanumerico_exacto",
        gold_sources=(GoldSource(doc_id="LAM-2-ALARMS", revision="B", pages=(12,)),),
    )
    chunk = "E-114 — Sobretemperatura del cojinete de salida. Umbral 95 °C."
    r = evaluate(c, respuesta("La alarma E-114 es sobretemperatura del cojinete de salida.",
                              text=chunk, doc="LAM-2-ALARMS", page=12, rev="B"))
    assert r["grounded"].passed is True


def test_codigo_inventado_si_falla_groundedness():
    c = Case(id="a", question="q", category="alfanumerico_exacto",
             gold_sources=(GoldSource(doc_id="D", pages=(1,)),))
    r = evaluate(c, respuesta("Ver la alarma E-999.", text="E-114 — Sobretemperatura.",
                              doc="D", page=1, rev=None))
    assert r["grounded"].passed is False
    assert "E-999" in r["grounded"].evidence["sin_respaldo"]


# ─────────────────────────────────────────────────────────────────────────────
# Normalizacion de numeros
# ─────────────────────────────────────────────────────────────────────────────
def test_no_confunde_un_substring_con_un_numero():
    # "30" NO esta en "1300": comparar substrings crudos daria por fundamentado un
    # numero que nunca estuvo.
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
def test_canonicalizacion(crudo, canonico):
    assert canonicalize(crudo) == canonico


def test_gold_number_con_otro_formato_igual_cuenta():
    # El set dice "680" y la respuesta escribe "680.0": es el mismo numero.
    r = evaluate(caso(), respuesta("El torque es 680.0 ± 30 N·m."))
    assert r["gold_numbers_present"].passed is True


# ─────────────────────────────────────────────────────────────────────────────
# Citas y revisiones
# ─────────────────────────────────────────────────────────────────────────────
def test_cita_a_la_pagina_equivocada_falla():
    r = evaluate(caso(), respuesta("680 ± 30 N·m", page=200))
    assert r["citation_hits_gold"].passed is False


def test_revision_supersedida_falla():
    r = evaluate(caso(), respuesta("680 ± 30 N·m", rev="B"))
    assert r["revision_current"].passed is False
    assert "supersedida" in r["revision_current"].detail
    assert r["revision_current"].evidence == {"vigentes": ["D"], "citadas": ["B"]}


def test_no_citar_nada_falla_la_cita():
    r = evaluate(caso(), Response(answer="680 ± 30 N·m", citations=()))
    assert r["citation_hits_gold"].passed is False
    assert r["citation_hits_gold"].detail == "no cito nada"


# ─────────────────────────────────────────────────────────────────────────────
# Reglas 2 y 3 de `numbers.py` — los tres defectos encontrados al etiquetar M3
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "token",
    ["9150-00-292-9689", "1.9.4", "14.2.29", "MIL-PRF-14107", "E-114", "M24", "QS-1", "12/07/2024"],
)
def test_identificadores_no_se_parten_en_numeros(token):
    assert extract_numbers(token) == []
    assert extract_codes(token) == [token.upper()]


@pytest.mark.parametrize("token", ["720", "30", "8.8", "68,5", "1.200", "1.200,50", "1.200.000"])
def test_los_numeros_siguen_siendo_numeros(token):
    assert [t.raw for t in extract_numbers(token)] == [token]
    assert extract_codes(token) == []


def test_una_version_equivocada_no_pasa_groundedness():
    """El falso positivo que la regla 2 evita — el peor de los tres defectos.

    Sin ella, `1.9.4` se partia en "1.9" y "4". Un sistema que contestara "Leaflet 1.9.5"
    pasaba `grounded` porque el chunk traia un 1.9 y algun 5 en otra parte: publicaba
    como fundamentado algo que no lo estaba.
    """
    c = Case(id="ver", question="¿Qué versión de Leaflet?", category="alfanumerico_exacto",
             gold_sources=(GoldSource(doc_id="TP", pages=(3,)),))
    chunk = "| Mapas | Leaflet 1.9.4 |\n| UI | React 18 |\n| Pagos | 5 métodos |"

    correcta = evaluate(c, respuesta("Usa Leaflet 1.9.4.", text=chunk, doc="TP", page=3, rev=None))
    assert correcta["grounded"].passed is True

    equivocada = evaluate(c, respuesta("Usa Leaflet 1.9.5.", text=chunk, doc="TP", page=3, rev=None))
    assert equivocada["grounded"].passed is False
    assert "1.9.5" in equivocada["grounded"].evidence["sin_respaldo"]


def test_un_nsn_inventado_no_pasa_groundedness():
    """Antes, un NSN no era ni número ni código: era invisible para `grounded`."""
    c = Case(id="nsn", question="¿NSN del aceite LAW?", category="alfanumerico_exacto",
             gold_sources=(GoldSource(doc_id="TM", pages=(126,)),))
    chunk = "| 9 | C | 9150-00-292-9689 | LUBRICATING OIL, WEAPONS LOW TEMPERATURE (LAW) |"

    ok = evaluate(c, respuesta("El NSN es 9150-00-292-9689.", text=chunk, doc="TM", page=126, rev=None))
    assert ok["grounded"].passed is True

    mal = evaluate(c, respuesta("El NSN es 9150-00-292-9999.", text=chunk, doc="TM", page=126, rev=None))
    assert mal["grounded"].passed is False


# ─────────────────────────────────────────────────────────────────────────────
# Reglas 4 y exención por enunciado — los dos falsos negativos que encontró M4
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("1) Notificar. 2) Abrir QS-1.", []),
        ("1. Primero  2. Segundo", []),
        ("| (3) NATIONAL STOCK NUMBER |", []),
        ("3 pasadas en cruz", ["3"]),          # un numero que afirma SI cuenta
        ("720 +/- 30 N.m", ["720", "30"]),
    ],
)
def test_los_marcadores_de_lista_no_son_numeros(texto, esperado):
    """Regla 4: un sistema que numera sus pasos no debe fallar groundedness por numerar."""
    assert [t.raw for t in extract_numbers(texto)] == esperado


def test_un_procedimiento_numerado_esta_fundamentado():
    c = Case(id="loto", question="¿Cuál es el procedimiento LOTO?", category="procedimental",
             gold_sources=(GoldSource(doc_id="D", pages=(1,)),))
    chunk = "Notificar a produccion y detener la linea.\nAbrir el seccionador QS-1."
    r = evaluate(c, respuesta("1) Notificar a produccion y detener la linea. 2) Abrir el "
                              "seccionador QS-1.", text=chunk, doc="D", page=1, rev=None))
    assert r["grounded"].passed is True


def test_un_numero_que_viene_en_la_pregunta_esta_exento():
    """Repetir el enunciado no es alucinar.

    La pregunta trae "15 mm"; la tabla habla de "hasta 20" y "mas de 20". Sin la exención,
    la respuesta correcta fallaría por citar el espesor que preguntó el usuario.
    """
    c = Case(
        id="delgado",
        question="¿Hay que precalentar el A516 Gr.70 de 15 mm de espesor?",
        category="factual_lookup",
        gold_sources=(GoldSource(doc_id="D", pages=(1,)),),
    )
    chunk = "| A516 Gr.70 | hasta 20 | ninguno |\n| A106 Gr.B | cualquiera | 80 |"
    r = evaluate(c, respuesta("El A516 Gr.70 de 15 mm no requiere precalentamiento.",
                              text=chunk, doc="D", page=1, rev=None))
    assert r["grounded"].passed is True
    assert "15" in r["grounded"].evidence["exentos_por_venir_en_la_pregunta"]


def test_la_exencion_no_deja_pasar_un_numero_inventado():
    c = Case(
        id="delgado",
        question="¿Hay que precalentar el A516 Gr.70 de 15 mm?",
        category="factual_lookup",
        gold_sources=(GoldSource(doc_id="D", pages=(1,)),),
    )
    chunk = "| A516 Gr.70 | hasta 20 | ninguno |"
    # El 15 esta exento; el 240 no, y no esta en el chunk.
    r = evaluate(c, respuesta("El A516 Gr.70 de 15 mm requiere 240 C.",
                              text=chunk, doc="D", page=1, rev=None))
    assert r["grounded"].passed is False
    assert r["grounded"].evidence["sin_respaldo"] == ["240"]


def test_el_control_negativo_no_se_escapa_por_la_exencion():
    """Preguntan por el M30: el `M30` queda exento, pero de la alucinación se ocupa
    `check_abstention`, que es su check. La división de trabajo importa."""
    c = Case(id="m30", question="¿Cuál es el par de apriete del perno M30 del cabezal?",
             category="negative_control", must_abstain=True,
             gold_sources=(GoldSource(doc_id="D", pages=(1,)),))
    chunk = "| M24 cabezal | 8.8 | 720 +/- 30 |\n| M16 tapa | 8.8 | 190 +/- 10 |"
    r = evaluate(c, respuesta("El par del M30 es 720 +/- 30 N.m.", text=chunk, doc="D",
                              page=1, rev=None))
    assert r["grounded"].passed is True            # el 720 esta literal en la tabla
    assert r["abstention_correct"].passed is False  # y acá se lo atrapa


# ─────────────────────────────────────────────────────────────────────────────
# forbidden_codes — el hueco del formato que M3 dejo anotado
# ─────────────────────────────────────────────────────────────────────────────
ALARMAS = (
    "| E-114 | Sobretemperatura de bobina        | Parar y purgar refrigerante |\n"
    "| E-115 | Perdida de caudal de refrigerante | Verificar bomba P-3         |\n"
    "| E-141 | Fallo de aislamiento              | Bloquear equipo             |\n"
)


def caso_alarma(**kw) -> Case:
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


def test_contestar_la_alarma_de_al_lado_lo_atrapa_forbidden_codes():
    """La trampa que `forbidden_numbers` NO puede ver.

    El "115" de E-115 vive dentro de un identificador y nunca se extrae como numero, asi
    que sin este check la respuesta equivocada pasaba entera: cita bien, esta fundamentada
    (la tabla trae las tres filas) y no trae ningun numero prohibido.
    """
    r = evaluate(caso_alarma(), respuesta(
        "La alarma E-115 indica perdida de caudal de refrigerante.",
        text=ALARMAS, doc="LAM", page=1, rev=None))
    assert r["forbidden_codes_absent"].passed is False
    assert "E-115" in r["forbidden_codes_absent"].evidence["presentes"]
    # Y se ve por que hacia falta: los otros checks la dejan pasar.
    assert r["grounded"].passed is True
    assert r["citation_hits_gold"].passed is True


def test_la_respuesta_correcta_pasa_forbidden_codes():
    r = evaluate(caso_alarma(), respuesta(
        "La alarma E-114 indica sobretemperatura de bobina.",
        text=ALARMAS, doc="LAM", page=1, rev=None))
    assert r["forbidden_codes_absent"].passed is True


def test_sin_codigos_prohibidos_el_check_es_None():
    r = evaluate(caso_alarma(forbidden_codes=()), respuesta(
        "La alarma E-114 indica sobretemperatura.", text=ALARMAS, doc="LAM", page=1, rev=None))
    assert r["forbidden_codes_absent"].passed is None


def test_los_codigos_prohibidos_comparan_sin_importar_mayusculas():
    r = evaluate(caso_alarma(forbidden_codes=("e-115",)), respuesta(
        "Ver E-115.", text=ALARMAS, doc="LAM", page=1, rev=None))
    assert r["forbidden_codes_absent"].passed is False


def test_un_codigo_prohibido_que_esta_en_la_respuesta_de_oro_es_error(tmp_path):
    """Seria una trampa contra la respuesta correcta: el caso fallaria siempre."""
    from assay.suite import SuiteError, load_suite

    body = (
        "cases:\n  - id: x\n    question: q\n    category: alfanumerico_exacto\n"
        "    gold_answer: 'Ver la alarma E-114'\n    forbidden_codes: ['E-114']\n"
    )
    p = tmp_path / "s.yaml"
    p.write_text(body, "utf-8")
    with pytest.raises(SuiteError, match="a la vez"):
        load_suite(p)
