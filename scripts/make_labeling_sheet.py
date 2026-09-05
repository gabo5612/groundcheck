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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assay.checks import evaluate  # noqa: E402
from assay.report import _response_from_json  # noqa: E402
from assay.suite import load_suite  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


def main(run_path: str, out_path: str | None = None) -> int:
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
        })

    lineas = [
        "# ═══════════════════════════════════════════════════════════════════════════",
        "# PLANILLA DE ETIQUETADO HUMANO — M7",
        "#",
        "# QUE HACER: por cada caso, escribi en `tu_veredicto` una de estas dos palabras:",
        "#",
        "#     bien   la respuesta es correcta y util para quien pregunto",
        "#     mal    la respuesta es incorrecta, incompleta o enganosa",
        "#",
        "# `por_que` es opcional, una linea. Nada mas. No mires lo que dicen los checks",
        "# deterministas si no querres: estan ahi como contexto, no como sugerencia.",
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
        lineas.append(f"    abstuvo: {str(f['abstuvo']).lower()}")
        lineas.append(f"    # checks deterministas → {f['checks']}")
        lineas.append(
            f"    los_deterministas_ya_lo_atraparon: {str(f['los_deterministas_ya_lo_atraparon']).lower()}"
        )
        lineas.append("    tu_veredicto:      # bien | mal")
        lineas.append("    por_que:           # opcional, una linea")

    salida = Path(out_path or (RAIZ / "judge" / "etiquetas-humanas.yaml"))
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text("\n".join(lineas) + "\n", "utf-8")

    obvios = sum(1 for f in filas if f["los_deterministas_ya_lo_atraparon"])
    print(f"escrito {salida}")
    print(f"  {len(filas)} casos para etiquetar")
    print(f"  {obvios} ya atrapados por los checks deterministas · {len(filas) - obvios} donde")
    print("  el juez es la unica forma de detectar un problema")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:3]))
