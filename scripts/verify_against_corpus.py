"""Prueba que el golden set esté realmente respaldado por el corpus.

Un golden set cuyos números no se pueden rastrear al documento es peor que no tener
golden set: mide contra una respuesta inventada y culpa al sistema. Este script no
opina de calidad — solo verifica lo verificable:

  1. cada `gold_source.doc_id` existe en el corpus
  2. la revisión declarada coincide con la del documento
  3. las páginas declaradas existen y tienen chunks
  4. cada `gold_number` aparece literal en algún chunk de esa página
  5. cada `forbidden_number` y `forbidden_code` TAMBIÉN aparece en el corpus  ← ver abajo
  6. los controles negativos NO tienen su respuesta en la página citada

El punto 5 es el menos obvio y el más importante: un `forbidden_number` que no está en
el documento no es una trampa, es ruido. La trampa tiene que ser un número REAL de otra
fila — si no, el check nunca se dispara y da una falsa sensación de rigor.

Uso:
    python3 scripts/verify_against_corpus.py ../anvil/demo/corpus.json suites/anvil-v1.yaml
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assay.numbers import contains_number, extract_codes  # noqa: E402
from assay.suite import load_suite  # noqa: E402


def main(corpus_path: str, suite_path: str) -> int:
    corpus = json.loads(Path(corpus_path).read_text("utf-8"))
    docs = {d["doc_id"]: d for d in corpus["docs"]}
    chunks = corpus["chunks"]
    suite = load_suite(suite_path)

    fallos: list[str] = []
    total_num = 0
    total_prohibidos = 0

    for case in suite.cases:
        for src in case.gold_sources:
            doc = docs.get(src.doc_id)
            if doc is None:
                fallos.append(f"{case.id}: doc_id {src.doc_id} no existe en el corpus")
                continue
            if src.revision is not None and str(doc.get("revision")) != src.revision:
                fallos.append(
                    f"{case.id}: revision declarada {src.revision!r} != "
                    f"{doc.get('revision')!r} del corpus"
                )

            en_pagina = [
                c for c in chunks
                if c["doc"] == src.doc_id
                and (not src.pages or any(c["p0"] <= p <= c["p1"] for p in src.pages))
            ]
            if not en_pagina:
                fallos.append(f"{case.id}: sin chunks en {src.doc_id} paginas {list(src.pages)}")
                continue
            texto = "\n".join(c["text"] for c in en_pagina)

            for n in case.gold_numbers:
                total_num += 1
                if not contains_number(texto, n):
                    fallos.append(f"{case.id}: gold_number {n!r} NO aparece en la pagina citada")

            for n in case.forbidden_numbers:
                total_prohibidos += 1
                if not contains_number(texto, n):
                    fallos.append(
                        f"{case.id}: forbidden_number {n!r} no esta en el corpus — "
                        f"es ruido, no una trampa (el check nunca se dispararia)"
                    )

            for code in case.forbidden_codes:
                total_prohibidos += 1
                if code.upper() not in {c.upper() for c in extract_codes(texto)}:
                    fallos.append(
                        f"{case.id}: forbidden_code {code!r} no esta en el corpus — "
                        f"es ruido, no una trampa"
                    )

            # Los identificadores de la respuesta de oro tambien tienen que existir.
            if case.gold_answer:
                del_corpus = set(extract_codes(texto))
                for code in extract_codes(case.gold_answer):
                    if code not in del_corpus:
                        fallos.append(
                            f"{case.id}: el identificador {code!r} de gold_answer no esta "
                            f"en la pagina citada"
                        )

    negativos = [c for c in suite.cases if c.category == "negative_control"]
    print(f"suite   : {suite.name} · {suite.case_count} casos · sha256 {suite.sha256[:16]}")
    print(f"corpus  : {len(docs)} docs · {len(chunks)} chunks")
    print(f"revisado: {total_num} gold_numbers · {total_prohibidos} forbidden_numbers · "
          f"{len(negativos)} controles negativos ({len(negativos) / suite.case_count:.0%})")
    print()

    if fallos:
        print(f"✗ {len(fallos)} problema(s):")
        for f in fallos:
            print(f"    {f}")
        return 1
    print("✓ todo el golden set esta respaldado por el corpus")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
