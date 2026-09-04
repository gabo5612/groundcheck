"""Extraccion de numeros y codigos del texto de una respuesta.

Este modulo es el que decide si `grounded` da verdadero o falso, asi que sus dos reglas
estan escritas explicitas:

**Regla 1 — un digito pegado a una letra no es un numero, es un codigo.**
`E-114` no aporta el numero 114, y `M24` no aporta el 24. Extraerlos como numeros haria
que la respuesta correcta *"La alarma E-114 indica sobretemperatura"* fallara groundedness
porque "114" no aparece suelto en el chunk. Ese falso negativo es peor que no medir: te
hace "arreglar" un sistema que estaba bien. Los codigos se extraen aparte y se comparan
como codigos.

**Regla 2 — la ambiguedad de `1.200` se documenta, no se adivina en silencio.**
En espanol es mil doscientos; en ingles, uno punto dos. La convencion elegida esta abajo,
con test, y el resultado de cada check guarda **el token crudo junto al canonico** para
que un humano pueda auditar cualquier desacuerdo sin leer el codigo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Un numero: digitos con separadores opcionales de miles/decimales. El lookaround es lo
# que implementa la regla 1 — nada de letras ni guiones-con-letra alrededor.
_NUMBER = re.compile(
    r"""
    (?<![A-Za-z0-9])          # ni letra ni digito antes
    (?<!-)                    # ni guion antes (E-114, ISO-9001)
    (\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d+)?   # con separador de miles: 1,200 · 1.200,50
     |\d+(?:[.,]\d+)?)                     # simple: 680 · 68,5 · 8.8
    (?![A-Za-z0-9])           # ni letra ni digito despues
    (?!-\d)                   # no es la primera mitad de un rango tipo 10-20
    """,
    re.VERBOSE,
)

# Un codigo: letras y digitos mezclados, con guiones opcionales. E-114 · M24 · WPS-014 ·
# LAM-2-MAINT · 8.8 NO (eso es un numero).
_CODE = re.compile(r"\b(?=[A-Za-z0-9-]*\d)(?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z]+-?\d+[A-Za-z0-9-]*\b")


@dataclass(frozen=True)
class NumberToken:
    raw: str
    canonical: str

    def __str__(self) -> str:  # pragma: no cover - conveniencia de debug
        return f"{self.raw}→{self.canonical}"


def canonicalize(raw: str) -> str:
    """Forma canonica de un numero escrito.

    Convencion, elegida y fijada con test:
    - Si aparecen `.` y `,` en el mismo token, **el ultimo es el decimal**
      (`1.200,50` → `1200.50`, `1,200.50` → `1200.50`). Esto no tiene ambiguedad.
    - Si aparece un solo separador **seguido por exactamente 3 digitos**, se lee como
      separador de miles (`1.200` → `1200`, `1,200` → `1200`).
      ⚠️ **Limitacion conocida y aceptada:** `68.500` se lee como `68500`, no como 68.5
      con ceros de relleno. En documentacion tecnica industrial el separador de miles es
      mucho mas frecuente que tres decimales, y la alternativa —adivinar por contexto—
      seria menos predecible. El token crudo queda guardado para poder auditarlo.
    - Cualquier otro separador unico es decimal (`68,5` → `68.5`).
    - Los espacios como separador de miles se eliminan (`1 200` → `1200`).
    - Los ceros de cola de un decimal se recortan (`680.0` → `680`) para que `680` y
      `680.0` no cuenten como numeros distintos.
    """
    token = raw.replace(" ", "").replace(" ", "")

    if "." in token and "," in token:
        decimal_sep = "." if token.rfind(".") > token.rfind(",") else ","
        thousands_sep = "," if decimal_sep == "." else "."
        token = token.replace(thousands_sep, "").replace(decimal_sep, ".")
    else:
        for sep in (".", ","):
            if sep in token:
                head, _, tail = token.rpartition(sep)
                if len(tail) == 3 and head.replace(sep, "").isdigit():
                    token = token.replace(sep, "")       # separador de miles
                else:
                    token = token.replace(sep, ".")      # decimal
                break

    if "." in token:
        token = token.rstrip("0").rstrip(".")
    return token or "0"


def extract_numbers(text: str | None) -> list[NumberToken]:
    if not text:
        return []
    return [NumberToken(raw=m.group(1), canonical=canonicalize(m.group(1))) for m in _NUMBER.finditer(text)]


def extract_codes(text: str | None) -> list[str]:
    """Codigos alfanumericos, normalizados a mayusculas."""
    if not text:
        return []
    return [m.group(0).upper() for m in _CODE.finditer(text)]


def contains_number(haystack: str | None, needle: str) -> bool:
    """El numero `needle` aparece en `haystack`, comparando en forma canonica.

    Se compara canonico contra canonico y no substring crudo a proposito: buscar "30"
    como substring lo encontraria dentro de "1300", y eso daria por fundamentado un
    numero que nunca estuvo.
    """
    objetivo = canonicalize(needle)
    return any(tok.canonical == objetivo for tok in extract_numbers(haystack))


def contains_code(haystack: str | None, needle: str) -> bool:
    return needle.upper() in extract_codes(haystack)
