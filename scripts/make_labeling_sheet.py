"""Genera la planilla de etiquetado humano para el LLM-judge (M7).

El juez se publica SIEMPRE junto a su tasa de acuerdo con etiquetas humanas (§4 del
spec). Esa tasa se mide contra el juicio de una persona: si la produjera un modelo,
seria un modelo juzgando a otro modelo, que es exactamente lo que este proyecto no hace.

La planilla incluye a proposito casos donde los checks deterministas PASAN. Ahi es donde
el juez tiene algo que aportar y donde su acuerdo con un humano es informativo; en un
caso donde el verificador ya dijo "numero inventado" no hace falta juez.

Uso:  python3 scripts/make_labeling_sheet.py <corrida.json> [salida.yaml]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assay.checks import evaluate  # noqa: E402
from assay.report import _response_from_json  # noqa: E402
from assay.suite import load_suite  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


def _pasajes_de_oro(corpus_path: str, caso) -> list[str]:
    """El texto del documento donde vive la respuesta correcta.

    Sin esto la planilla pide juzgar una respuesta sin dar contra que juzgarla, que es
    pedir una opinion, no una etiqueta.
    """
    if not corpus_path or not Path(corpus_path).exists():
        return []
    corpus = json.loads(Path(corpus_path).read_text("utf-8"))
    out = []
    for src in caso.gold_sources:
        for c in corpus["chunks"]:
            if c["doc"] != src.doc_id:
                continue
            if src.pages and not any(c["p0"] <= pg <= c["p1"] for pg in src.pages):
                continue
            texto = " ".join(c["text"].split())
            if len(texto) > 40:
                out.append(texto[:600])
    return out[:3]


def main(run_path: str, out_path: str | None = None, corpus_path: str = "") -> int:
    run = json.loads(Path(run_path).read_text("utf-8"))
    suite = load_suite(run["suite"]["path"] if Path(run["suite"]["path"]).exists()
                       else RAIZ / "suites" / "anvil-v1.yaml")
    casos = {c.id: c for c in suite.cases}

    filas = []
    for obs in run["observations"]:
        caso = casos.get(obs["case_id"])
        if caso is None:
            continue
        resp = _response_from_json(obs.get("response"))
        checks = evaluate(caso, resp)
        veredictos = {n: r.passed for n, r in checks.items()}
        fallo_algo = any(v is False for v in veredictos.values())

        resumen = " · ".join(
            f"{n.replace('_', ' ')}: {'ok' if v else 'FALLA' if v is False else 'n/a'}"
            for n, v in veredictos.items()
        )
        filas.append({
            "id": caso.id,
            "categoria": caso.category,
            "pregunta": caso.question,
            "respuesta": (resp.answer if resp else None),
            "abstuvo": bool(resp and resp.abstained),
            "esperado": caso.gold_answer,
            "checks": resumen,
            "los_deterministas_ya_lo_atraparon": fallo_algo,
            "razon": (resp.reason if resp else None),
            "fuente": _pasajes_de_oro(corpus_path, caso),
            "doc": (caso.gold_sources[0].doc_id if caso.gold_sources else None),
            "pagina": (list(caso.gold_sources[0].pages) if caso.gold_sources else []),
        })

    lineas = [
        "# ═══════════════════════════════════════════════════════════════════════════",
        "# PLANILLA DE ETIQUETADO HUMANO — M7",
        "#",
        "# QUE HACER: compara la `respuesta` contra el bloque `fuente`, que es el texto",
        "# LITERAL del documento donde vive la respuesta correcta. Despues escribi en",
        "# `tu_veredicto` una de estas dos palabras:",
        "#",
        "#     bien   la respuesta es correcta y util para quien pregunto",
        "#     mal    la respuesta es incorrecta, incompleta o enganosa",
        "#",
        "# `por_que` es opcional, una linea.",
        "#",
        "# LA REGLA: si la respuesta dice algo que la fuente NO dice, es `mal`, por bien",
        "# escrita que este. Si la pregunta es un control negativo (el dato no existe en la",
        "# documentacion), la unica respuesta correcta es abstenerse: si contesta con una",
        "# cifra, es `mal` aunque la cifra exista en otra fila.",
        "#",
        "# PARA QUE SIRVE: con estas etiquetas se calcula la TASA DE ACUERDO entre vos y",
        "# el LLM-judge, y esa tasa se publica al lado de cada numero del juez. Un juez sin",
        "# su tasa de acuerdo es una opinion con decimales (§4 del spec).",
        "#",
        "# OJO CON LOS CASOS MARCADOS `los_deterministas_ya_lo_atraparon: true`: ahi el",
        "# verificador YA dijo que hay algo mal. Igual etiquetalos — sirven para ver si el",
        "# juez coincide en lo obvio antes de creerle en lo sutil.",
        "# ═══════════════════════════════════════════════════════════════════════════",
        "",
        "etiquetas:",
    ]

    for f in filas:
        lineas.append("")
        lineas.append(f"  - id: {f['id']}")
        lineas.append(f"    categoria: {f['categoria']}")
        lineas.append(f"    pregunta: {json.dumps(f['pregunta'], ensure_ascii=False)}")
        lineas.append(f"    respuesta: {json.dumps(f['respuesta'], ensure_ascii=False)}")
        if f["esperado"]:
            lineas.append(f"    esperado: {json.dumps(f['esperado'], ensure_ascii=False)}")
        else:
            lineas.append("    esperado: null   # CONTROL NEGATIVO: lo correcto es abstenerse")
        if f["fuente"]:
            lineas.append(f"    # ── FUENTE (doc {str(f['doc'])[:8]}, pagina {f['pagina']}) "
                          "— el documento dice literalmente:")
            for pas in f["fuente"]:
                lineas.append(f"    #   {pas}")
        lineas.append(f"    abstuvo: {str(f['abstuvo']).lower()}")
        if f.get("razon"):
            # Lo que el sistema dijo cuando no dio una respuesta. Sin esto, una abstencion
            # correcta se lee como una respuesta vacia y se etiqueta "mal" con razon.
            lineas.append(f"    lo_que_dijo_el_sistema: {json.dumps(f['razon'], ensure_ascii=False)}")
        lineas.append(f"    # checks deterministas → {f['checks']}")
        lineas.append(
            f"    los_deterministas_ya_lo_atraparon: {str(f['los_deterministas_ya_lo_atraparon']).lower()}"
        )
        lineas.append("    tu_veredicto:      # bien | mal")
        lineas.append("    por_que:           # opcional, una linea")

    # MUESTRA, no el set entero. La tasa de acuerdo se mide sobre una muestra (§4 del
    # spec) y etiquetar 39 casos a mano garantiza que los ultimos se llenen sin leer —
    # que es peor que tener menos etiquetas. Se priorizan los casos donde los checks
    # deterministas NO detectaron nada: ahi el juez es la unica red, y su acuerdo con un
    # humano es lo informativo. Se dejan unos pocos ya atrapados como control.
    limite = int(os.environ.get("ASSAY_MUESTRA", "12"))
    solo_juez = [f for f in filas if not f["los_deterministas_ya_lo_atraparon"]]
    ya_obvios = [f for f in filas if f["los_deterministas_ya_lo_atraparon"]]
    filas = (solo_juez + ya_obvios)[:limite]

    salida = Path(out_path or (RAIZ / "judge" / "etiquetas-humanas.yaml"))
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text("\n".join(lineas) + "\n", "utf-8")

    obvios = sum(1 for f in filas if f["los_deterministas_ya_lo_atraparon"])
    print(f"escrito {salida}")
    print(f"  {len(filas)} casos para etiquetar (muestra; ASSAY_MUESTRA para cambiar)")
    print(f"  {len(filas) - obvios} donde el juez es la unica red · {obvios} de control")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:4]))
