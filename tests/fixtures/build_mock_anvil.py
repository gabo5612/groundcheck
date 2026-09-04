"""Genera `mock_anvil.yaml`: un sistema guionado que responde las 20 preguntas de
`suites/anvil-v1.yaml`.

**Esto NO es una medición de anvil.** Es una ficción deliberada, escrita para que cada
check del harness se dispare al menos una vez y para que el reporte de M4 se pueda ver
lleno antes de que exista una corrida real. Los textos de los chunks salen del corpus de
verdad (para no introducir errores de transcripción); las respuestas y los fallos son
inventados a propósito, caso por caso, y la intención de cada uno está escrita al lado.

Uso:
    python3 tests/fixtures/build_mock_anvil.py ../anvil/demo/corpus.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAM2, TM, TP = "c0d5f95f636967d1", "75b2742de4b3a05f", "3f328ec9cc2bb39f"

# (pregunta_id, respuesta, [chunks citados], abstenida, revision_citada, nota de intencion)
INTENTS = [
    ("torque-m24-grado-88",
     "El par de apriete del perno M24 del cabezal en grado 8.8 es 720 +/- 30 N.m, "
     "en secuencia cruzada, 3 pasadas.",
     ["Pares de apriete del cabezal\n"], False, "F", "correcta y completa: pasa los seis checks"),

    ("torque-m24-grado-109",
     "El par de apriete del M24 del cabezal es 720 +/- 30 N.m.",
     ["Pares de apriete del cabezal\n"], False, "F",
     "CRUZO FILAS: da la fila del 8.8 cuando se pidio 10.9. grounded PASA (el 720 esta "
     "literal en la tabla) y es forbidden_numbers el que lo atrapa. El caso que justifica "
     "tener los dos checks"),

    ("torque-m16-tapa",
     "El perno M16 de la tapa lleva 190 +/- 10 N.m, cruzada, 2 pasadas.",
     ["Pares de apriete del cabezal\n"], False, "B",
     "respuesta correcta pero CITA LA REVISION B, que esta supersedida (el doc es rev F). "
     "Muestra que revision_current es independiente de citation_hits_gold"),

    ("precalentamiento-a516-espeso",
     "Para el A516 Gr.70 en espesores mayores a 20 mm se requiere precalentamiento a 95 C.",
     ["Espesor (mm)"], False, "F", "correcta"),

    ("precalentamiento-a106",
     "El A106 Gr.B requiere precalentamiento a 80 C para cualquier espesor.",
     ["Espesor (mm)"], False, "F", "correcta"),

    ("precalentamiento-a516-delgado",
     "El A516 Gr.70 de 15 mm requiere precalentamiento a 80 C.",
     ["Espesor (mm)"], False, "F",
     "INVENTA UN NUMERO donde la respuesta correcta es 'ninguno'. El 80 es la fila del "
     "A106: forbidden_numbers lo atrapa. grounded pasa porque el 80 esta en la tabla"),

    ("pasadas-cabezal",
     "Los pernos del cabezal se aprietan en patron cruzado, en 3 pasadas.",
     ["Pares de apriete del cabezal\n", "patron cruzado"], False, "F", "correcta"),

    ("version-leaflet-trailkit",
     "El sitio de TrailKit usa Leaflet 1.9.5.",
     ["Leaflet"], False, None,
     "VERSION EQUIVOCADA (1.9.5 en vez de 1.9.4). Antes del arreglo de M3 esto PASABA "
     "groundedness porque 1.9.4 se partia en '1.9' y '4'. Es el falso positivo que se cerro"),

    ("alarma-e114",
     "La alarma E-114 indica sobretemperatura de bobina. Accion: parar y purgar refrigerante.",
     ["E-114"], False, "F", "correcta"),

    ("alarma-e115-accion",
     "Ante la alarma E-115 hay que verificar la bomba P-3, por perdida de caudal de refrigerante.",
     ["E-114"], False, "F", "correcta (el chunk de alarmas trae las tres filas)"),

    ("nsn-aceite-law",
     "The National Stock Number is 9150-00-292-9689.",
     ["9150-00-292-9689"], False, "A",
     "correcta, en el documento largo de 117 paginas y en ingles"),

    ("seccionador-loto",
     "Se abre el seccionador principal QS-1, verificando ausencia de tension.",
     ["QS-1 y verificar"], False, "F", "correcta"),

    ("loto-linea-colada-completo",
     "1) Notificar a produccion y detener la linea. 2) Abrir el seccionador principal QS-1 "
     "y verificar ausencia de tension. 3) Colocar candado personal y tarjeta de "
     "identificacion en QS-1. 4) Purgar la linea hidraulica y confirmar presion cero en el "
     "manometro PI-7. 5) Verificar enclavamiento antes de iniciar la intervencion.",
     ["Notificar a produccion", "QS-1 y verificar", "candado personal", "PI-7", "enclavamiento"],
     False, "F", "correcta y completa: los cinco pasos"),

    ("loto-presion-cero",
     "La presion cero se confirma en el manometro PI-7, despues de purgar la linea hidraulica.",
     ["PI-7"], False, "F", "correcta"),

    ("loto-primer-paso",
     "El primer paso es abrir el seccionador principal QS-1 y verificar ausencia de tension.",
     ["QS-1 y verificar"], False, "F",
     "PASO EQUIVOCADO: devuelve el segundo paso como si fuera el primero. NINGUN check "
     "determinista lo atrapa — cita bien, esta fundamentado y no trae numeros prohibidos. "
     "Es exactamente para lo que existe el LLM-judge de M7, y por eso M7 reporta sin bloquear"),

    ("montaje-cabezal-superficies",
     "Hay que verificar que las superficies esten libres de cascarilla.",
     ["cascarilla"], False, "F", "correcta"),

    ("torque-m30-inexistente",
     "El par de apriete del perno M30 del cabezal es 720 +/- 30 N.m.",
     ["Pares de apriete del cabezal\n"], False, "F",
     "ALUCINACION en un control negativo: el M30 no existe en la Tabla 4-7 y contesta con "
     "la fila del M24 'por cercania'. Es el fallo mas grave que mide el harness"),

    ("torque-m24-grado-129-inexistente",
     "No encontre el par de apriete para el M24 en grado 12.9 en la documentacion. "
     "La Tabla 4-7 solo especifica los grados 8.8 y 10.9.",
     ["Pares de apriete del cabezal\n"], True, "F",
     "se abstiene correctamente, y ademas explica por que: el comportamiento deseado"),

    ("alarma-e200-inexistente",
     "No figura ninguna alarma E-200 en la documentacion del horno de induccion.",
     ["E-114"], True, "F", "se abstiene correctamente"),

    ("precalentamiento-a312-inexistente",
     "El A312 requiere precalentamiento a 80 C antes de soldar.",
     ["Espesor (mm)"], False, "F",
     "ALUCINACION en el segundo control negativo: el A312 no esta en la tabla de 6.2"),
]

DOC_POR_CASO = {
    "nsn-aceite-law": TM,
    "version-leaflet-trailkit": TP,
}


def main(corpus_path: str) -> int:
    corpus = json.loads(Path(corpus_path).read_text("utf-8"))
    suite_path = Path(__file__).resolve().parents[2] / "suites" / "anvil-v1.yaml"
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    from assay.suite import load_suite

    suite = load_suite(suite_path)
    casos = {c.id: c for c in suite.cases}
    chunks = corpus["chunks"]

    def buscar(doc_id: str, aguja: str) -> dict:
        for c in chunks:
            if c["doc"] == doc_id and aguja in c["text"]:
                return c
        raise SystemExit(f"no encontre un chunk de {doc_id} con {aguja!r}")

    lineas = [
        "# ═══════════════════════════════════════════════════════════════════════════",
        "# GENERADO por tests/fixtures/build_mock_anvil.py — no editar a mano.",
        "#",
        "# Sistema GUIONADO que responde las 20 preguntas de suites/anvil-v1.yaml.",
        "#",
        "# ⚠️  ESTO NO ES UNA MEDICION DE anvil. Es una ficcion deliberada: los textos de",
        "#     los chunks salen del corpus real, pero las respuestas y sus fallos estan",
        "#     inventados caso por caso para que cada check se dispare al menos una vez.",
        "#     Cualquier numero que salga de correr esto mide al mock, no a anvil.",
        "# ═══════════════════════════════════════════════════════════════════════════",
        "responses:",
    ]

    for case_id, answer, agujas, abstained, revision, nota in INTENTS:
        caso = casos[case_id]
        doc_id = DOC_POR_CASO.get(case_id, LAM2)
        citados = [buscar(doc_id, a) for a in agujas]
        pregunta = json.dumps(caso.question, ensure_ascii=False)

        lineas.append(f"\n  # {case_id} — {nota}")
        lineas.append(f"  {pregunta}:")
        lineas.append(f"    answer: {json.dumps(answer, ensure_ascii=False)}")
        lineas.append(f"    abstained: {str(abstained).lower()}")
        lineas.append("    citations:")
        for c in citados:
            lineas.append(f"      - doc_id: {doc_id}")
            lineas.append(f"        page: {c['p0']}")
            if revision is not None:
                lineas.append(f"        revision: {revision}")
            lineas.append(f"        chunk_id: \"{c['id']}\"")
            lineas.append(f"        text: {json.dumps(c['text'], ensure_ascii=False)}")
        lineas.append("    retrieved:")
        for c in citados:
            lineas.append(
                f"      - {{doc_id: {doc_id}, page: {c['p0']}, chunk_id: \"{c['id']}\"}}"
            )

    out = Path(__file__).with_name("mock_anvil.yaml")
    out.write_text("\n".join(lineas) + "\n", "utf-8")
    print(f"escrito {out} · {len(INTENTS)} respuestas guionadas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "../anvil/demo/corpus.json"))
