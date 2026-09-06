"""Generates the human labelling sheet for the LLM judge (M7).

The judge is ALWAYS published alongside its agreement rate with human labels (§4 of the
spec). That rate is measured against a person's judgement: if a model produced it, it would
be a model judging another model, which is exactly what this project does not do.

The sheet deliberately includes cases where the deterministic checks PASS. That is where the
judge has something to contribute and where its agreement with a human is informative; in a
case where the verifier already said "invented number", no judge is needed.

Usage:  python3 scripts/make_labeling_sheet.py <run.json> [output.yaml] [corpus.json]
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
    """The document text where the correct answer lives.

    Without this the sheet asks someone to judge an answer without giving them anything to
    judge it against — which is asking for an opinion, not a label.
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
        "# HUMAN LABELLING SHEET — M7",
        "#",
        "# WHAT TO DO: compare `respuesta` against the `fuente` block, which is the",
        "# LITERAL text of the document where the correct answer lives. Then write one",
        "# of these two words in `tu_veredicto`:",
        "#",
        "#     bien   the answer is correct and useful to whoever asked",
        "#     mal    the answer is incorrect, incomplete or misleading",
        "#",
        "# `por_que` is optional, one line.",
        "#",
        "# THE RULE: if the answer says something the source does NOT say, it is `mal`, however",
        "# well written. If the question is a negative control (the fact does not exist in the",
        "# documentation), the only correct answer is to abstain: if it answers with a figure,",
        "# it is `mal` even when that figure exists in another row.",
        "#",
        "# WHY IT MATTERS: these labels are used to compute the AGREEMENT RATE between you and",
        "# the LLM judge, and that rate is published next to every number the judge produces. A",
        "# judge without its agreement rate is an opinion with decimals (§4 of the spec).",
        "#",
        "# WATCH THE CASES MARKED `los_deterministas_ya_lo_atraparon: true`: there the verifier",
        "# ALREADY said something is wrong. Label them anyway — they show whether the judge",
        "# agrees on the obvious before you trust it on the subtle.",
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
            lineas.append("    esperado: null   # NEGATIVE CONTROL: the correct behaviour is to abstain")
        if f["fuente"]:
            lineas.append(f"    # ── SOURCE (doc {str(f['doc'])[:8]}, page {f['pagina']}) "
                          "— the document says literally:")
            for pas in f["fuente"]:
                lineas.append(f"    #   {pas}")
        lineas.append(f"    abstuvo: {str(f['abstuvo']).lower()}")
        if f.get("razon"):
            # What the system said when it gave no answer. Without this, a correct
            # abstention reads as an empty answer and gets labelled "wrong", reasonably.
            lineas.append(f"    lo_que_dijo_el_sistema: {json.dumps(f['razon'], ensure_ascii=False)}")
        lineas.append(f"    # checks deterministas → {f['checks']}")
        lineas.append(
            f"    los_deterministas_ya_lo_atraparon: {str(f['los_deterministas_ya_lo_atraparon']).lower()}"
        )
        lineas.append("    tu_veredicto:      # bien | mal")
        lineas.append("    por_que:           # optional, one line")

    # A SAMPLE, not the whole set. The agreement rate is measured over a sample (§4 of the
    # spec), and hand-labelling 39 cases guarantees the last ones get filled in without
    # being read — which is worse than having fewer labels. Priority goes to cases where the
    # deterministic checks caught NOTHING: there the judge is the only net, and its agreement
    # with a human is what is informative. A few already-caught ones are kept as a control.
    limite = int(os.environ.get("ASSAY_MUESTRA", "12"))
    solo_juez = [f for f in filas if not f["los_deterministas_ya_lo_atraparon"]]
    ya_obvios = [f for f in filas if f["los_deterministas_ya_lo_atraparon"]]
    filas = (solo_juez + ya_obvios)[:limite]

    salida = Path(out_path or (RAIZ / "judge" / "etiquetas-humanas.yaml"))
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text("\n".join(lineas) + "\n", "utf-8")

    obvios = sum(1 for f in filas if f["los_deterministas_ya_lo_atraparon"])
    print(f"escrito {salida}")
    print(f"  {len(filas)} cases to label (a sample; set ASSAY_MUESTRA to change)")
    print(f"  {len(filas) - obvios} where the judge is the only net · {obvios} as control")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:4]))
