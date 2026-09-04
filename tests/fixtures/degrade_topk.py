"""Genera `mock_anvil_topk1.yaml`: el mismo sistema guionado, pero con top-k bajado a 1.

Es la regresión que pide el criterio de aceptación de M5. Simula el cambio de config más
banal y más común de un RAG —"traigamos menos chunks, va más rápido"— y deja todo lo demás
idéntico: las mismas respuestas, las mismas citas. Solo se trunca `retrieved`.

Así la caída que detecte el gate es atribuible a UNA causa y no a una mezcla.

Uso:  python3 tests/fixtures/degrade_topk.py [k]
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

AQUI = Path(__file__).resolve().parent


def main(k: int = 1) -> int:
    doc = yaml.safe_load((AQUI / "mock_anvil.yaml").read_text("utf-8"))
    truncados = 0
    for respuesta in doc["responses"].values():
        recuperados = respuesta.get("retrieved") or []
        if len(recuperados) > k:
            respuesta["retrieved"] = recuperados[:k]
            truncados += 1

    salida = AQUI / f"mock_anvil_topk{k}.yaml"
    salida.write_text(
        "# GENERADO por tests/fixtures/degrade_topk.py — no editar a mano.\n"
        f"# El mismo sistema guionado que mock_anvil.yaml, con top-k = {k}.\n"
        "# Unica diferencia: `retrieved` truncado. Respuestas y citas identicas, para que\n"
        "# la caida que detecte el gate sea atribuible a una sola causa.\n"
        + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
        "utf-8",
    )
    print(f"escrito {salida.name} · {truncados} respuestas con `retrieved` truncado a {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 1))
