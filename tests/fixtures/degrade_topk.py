"""Generates `mock_shopfloor_topk1.yaml`: the same scripted system, with top-k dropped to 1.

This is the regression the M5 acceptance criterion asks for. It simulates the most banal and
most common RAG config change — "fetch fewer chunks, it's faster" — and leaves everything
else identical: same answers, same citations. Only `retrieved` is truncated.

That way the drop the gate detects is attributable to ONE cause and not to a mixture.

Usage:  python3 tests/fixtures/degrade_topk.py [k]
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

AQUI = Path(__file__).resolve().parent


def main(k: int = 1) -> int:
    doc = yaml.safe_load((AQUI / "mock_shopfloor.yaml").read_text("utf-8"))
    truncados = 0
    for respuesta in doc["responses"].values():
        recuperados = respuesta.get("retrieved") or []
        if len(recuperados) > k:
            respuesta["retrieved"] = recuperados[:k]
            truncados += 1

    salida = AQUI / f"mock_shopfloor_topk{k}.yaml"
    salida.write_text(
        "# GENERADO por tests/fixtures/degrade_topk.py — no editar a mano.\n"
        f"# El mismo sistema guionado que mock_shopfloor.yaml, con top-k = {k}.\n"
        "# Unica diferencia: `retrieved` truncado. Respuestas y citas identicas, para que\n"
        "# la caida que detecte el gate sea atribuible a una sola causa.\n"
        + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
        "utf-8",
    )
    print(f"escrito {salida.name} · {truncados} respuestas con `retrieved` truncado a {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 1))
