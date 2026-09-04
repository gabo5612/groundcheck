"""Criterio de aceptacion de M1: recall@k, MRR y precision@k sobre un caso construido a
mano cuyo resultado se conoce de antemano.

Los valores esperados de este archivo estan calculados a mano y escritos como fraccion
exacta al lado de cada assert. No salen de correr el codigo y copiar lo que dio — que es
la forma mas comun de escribir un test de metricas que no prueba nada.
"""

import pytest

from assay.metrics import (
    RetrievedItem,
    matches,
    mean,
    mrr,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    relevance_vector,
)


def items(*specs) -> list[RetrievedItem]:
    """`items(("DOC", 147), ...)` en orden de rank, 1-based."""
    return [
        RetrievedItem(rank=i, doc_id=doc, page=page)
        for i, (doc, page) in enumerate(specs, start=1)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# CASO A — un solo objetivo de oro, el chunk correcto aparece en la posicion 3
#
#   objetivo: LAM-2-MAINT pagina 147
#
#   rank  documento          pagina   relevante?
#   ────  ─────────────────  ──────   ──────────
#     1   LAM-2-ALARMS         12        no
#     2   LAM-2-MAINT         150        no      <- doc correcto, pagina equivocada
#     3   LAM-2-MAINT         147        SI
#     4   LAM-2-MAINT         147        si      <- duplicado a proposito
#     5   OTRO                  1        no
#
#   vector de relevancia: [F, F, T, T, F]
# ─────────────────────────────────────────────────────────────────────────────
CASO_A = items(
    ("LAM-2-ALARMS", 12),
    ("LAM-2-MAINT", 150),
    ("LAM-2-MAINT", 147),
    ("LAM-2-MAINT", 147),
    ("OTRO", 1),
)
OBJETIVO_A = [("LAM-2-MAINT", (147,))]


def test_caso_A_vector_de_relevancia():
    assert relevance_vector(CASO_A, OBJETIVO_A) == [False, False, True, True, False]


def test_caso_A_recall():
    assert recall_at_k(CASO_A, OBJETIVO_A, 1) == 0.0          # 0 de 1 objetivo
    assert recall_at_k(CASO_A, OBJETIVO_A, 2) == 0.0          # 0 de 1
    assert recall_at_k(CASO_A, OBJETIVO_A, 3) == 1.0          # 1 de 1
    assert recall_at_k(CASO_A, OBJETIVO_A, 5) == 1.0          # 1 de 1


def test_caso_A_precision():
    assert precision_at_k(CASO_A, OBJETIVO_A, 1) == 0.0       # 0/1
    assert precision_at_k(CASO_A, OBJETIVO_A, 3) == pytest.approx(1 / 3)
    assert precision_at_k(CASO_A, OBJETIVO_A, 4) == pytest.approx(2 / 4)
    assert precision_at_k(CASO_A, OBJETIVO_A, 5) == pytest.approx(2 / 5)


def test_caso_A_reciprocal_rank():
    # Primer relevante en la posicion 3 -> 1/3
    assert reciprocal_rank(CASO_A, OBJETIVO_A) == pytest.approx(1 / 3)


def test_caso_A_precision_divide_por_k_no_por_lo_recuperado():
    """La decision 1 del modulo, como test.

    Con k=10 y solo 5 items recuperados, el denominador sigue siendo 10. Si alguien lo
    cambia a `min(k, len(retrieved))` los numeros de todas las corridas anteriores dejan
    de ser comparables, asi que el cambio tiene que romper un test.
    """
    assert precision_at_k(CASO_A, OBJETIVO_A, 10) == pytest.approx(2 / 10)


# ─────────────────────────────────────────────────────────────────────────────
# CASO B — dos objetivos (multi_documento): la respuesta vive en dos fuentes
#
#   objetivos: LAM-2-MAINT p147  ·  ITP-9 p3
#
#   rank  documento      pagina   cubre
#     1   LAM-2-MAINT      147    objetivo 1
#     2   RUIDO              9    —
#     3   ITP-9              3    objetivo 2
# ─────────────────────────────────────────────────────────────────────────────
CASO_B = items(("LAM-2-MAINT", 147), ("RUIDO", 9), ("ITP-9", 3))
OBJETIVOS_B = [("LAM-2-MAINT", (147,)), ("ITP-9", (3,))]


def test_caso_B_recall_cuenta_objetivos_cubiertos():
    assert recall_at_k(CASO_B, OBJETIVOS_B, 1) == 0.5         # 1 de 2 objetivos
    assert recall_at_k(CASO_B, OBJETIVOS_B, 2) == 0.5         # 1 de 2
    assert recall_at_k(CASO_B, OBJETIVOS_B, 3) == 1.0         # 2 de 2


def test_caso_B_precision_y_rr():
    assert precision_at_k(CASO_B, OBJETIVOS_B, 3) == pytest.approx(2 / 3)
    assert reciprocal_rank(CASO_B, OBJETIVOS_B) == 1.0        # relevante en posicion 1


def test_un_chunk_repetido_no_infla_el_recall():
    """La decision 2 del modulo, como test.

    Dos copias del mismo chunk cubren UN objetivo, no dos. Contar items relevantes en vez
    de objetivos cubiertos daria 1.0 acá, y ese es el bug clasico que infla el numero.
    """
    duplicados = items(("LAM-2-MAINT", 147), ("LAM-2-MAINT", 147))
    assert recall_at_k(duplicados, OBJETIVOS_B, 2) == 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Reglas de emparejamiento y de ausencia
# ─────────────────────────────────────────────────────────────────────────────
def test_sin_pagina_reportada_no_hay_credito_a_nivel_de_pagina():
    sin_pagina = [RetrievedItem(rank=1, doc_id="LAM-2-MAINT", page=None)]
    assert matches(sin_pagina[0], "LAM-2-MAINT", (147,)) is False
    # Si el objetivo no exige pagina, el mismo item si cuenta.
    assert matches(sin_pagina[0], "LAM-2-MAINT", ()) is True


def test_objetivo_sin_paginas_empareja_por_documento():
    assert recall_at_k(CASO_A, [("LAM-2-MAINT", ())], 2) == 1.0   # rank 2 es del doc


def test_sin_objetivos_las_metricas_son_None_no_cero():
    """La decision 3 del modulo, como test: los controles negativos dan `None`.

    Un cero se promedia y arrastra la media con un dato que no existe.
    """
    assert recall_at_k(CASO_A, [], 5) is None
    assert precision_at_k(CASO_A, [], 5) is None
    assert reciprocal_rank(CASO_A, []) is None


def test_nada_relevante_da_rr_cero_no_None():
    # Distinto del caso anterior: acá SI habia objetivo y el sistema no lo trajo. Eso es
    # un cero legitimo y tiene que promediarse como cero.
    assert reciprocal_rank(items(("RUIDO", 1)), OBJETIVO_A) == 0.0
    assert recall_at_k(items(("RUIDO", 1)), OBJETIVO_A, 5) == 0.0


def test_retrieved_vacio_no_revienta():
    assert recall_at_k([], OBJETIVO_A, 5) == 0.0
    assert precision_at_k([], OBJETIVO_A, 5) == 0.0
    assert reciprocal_rank([], OBJETIVO_A) == 0.0


def test_k_invalido_es_error():
    for k in (0, -1):
        with pytest.raises(ValueError, match="k tiene que ser"):
            recall_at_k(CASO_A, OBJETIVO_A, k)
        with pytest.raises(ValueError, match="k tiene que ser"):
            precision_at_k(CASO_A, OBJETIVO_A, k)


# ─────────────────────────────────────────────────────────────────────────────
# Agregacion
# ─────────────────────────────────────────────────────────────────────────────
def test_mean_ignora_los_None():
    # Tres casos, uno sin metrica (control negativo): promedio sobre 2, no sobre 3.
    assert mean([1.0, None, 0.0]) == 0.5
    assert mean([None, None]) is None
    assert mean([]) is None


def test_mrr_sobre_los_dos_casos_a_mano():
    # RR del caso A = 1/3 · RR del caso B = 1  ->  MRR = (1/3 + 1) / 2 = 2/3
    resultado = mrr([CASO_A, CASO_B], [OBJETIVO_A, OBJETIVOS_B])
    assert resultado == pytest.approx((1 / 3 + 1.0) / 2)
    assert resultado == pytest.approx(2 / 3)


def test_mrr_excluye_controles_negativos_del_promedio():
    # Tres casos, el del medio es control negativo (sin objetivos) -> promedio sobre 2.
    resultado = mrr([CASO_A, CASO_A, CASO_B], [OBJETIVO_A, [], OBJETIVOS_B])
    assert resultado == pytest.approx(2 / 3)


def test_mrr_exige_la_misma_cantidad_de_casos_y_objetivos():
    # `strict=True` en el zip: desalinear corridas y objetivos daria un MRR plausible
    # calculado sobre los pares equivocados, y eso es peor que un error.
    with pytest.raises(ValueError):
        mrr([CASO_A, CASO_B], [OBJETIVO_A])


def test_desde_raw_construye_los_items():
    raw = [{"doc_id": "D", "page": 7, "chunk_id": "c1"}, "solo-un-id", {"page": "no-entero"}]
    construidos = [RetrievedItem.from_raw(r, i) for i, r in enumerate(raw, start=1)]
    assert construidos[0] == RetrievedItem(rank=1, doc_id="D", page=7, chunk_id="c1")
    assert construidos[1].chunk_id == "solo-un-id" and construidos[1].doc_id is None
    assert construidos[2].page is None       # una pagina no entera se descarta, no rompe
