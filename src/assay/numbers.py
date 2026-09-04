"""Extraccion de numeros e identificadores del texto de una respuesta.

Este modulo decide si `grounded` da verdadero o falso, asi que sus reglas estan escritas
explicitas. Las tres primeras salieron de **intentar etiquetar el golden set (M3) y ver
que fallaba**, no de imaginar casos:

**Regla 1 — un digito pegado a una letra no es un numero, es un identificador.**
`E-114` no aporta el numero 114 ni `M24` el 24. Extraerlos como numeros haria que la
respuesta *correcta* "la alarma E-114 indica sobretemperatura" diera `grounded: false`
porque "114" no aparece suelto en el chunk. Ese falso negativo manda a arreglar un sistema
sano.

**Regla 2 — un token con tres o mas grupos separados es un identificador, no varios
numeros.** `1.9.4` no son "1.9 y 4", y `9150-00-292-9689` (un NSN) no es nada partido en
pedazos. Sin esta regla, un sistema que contestara "Leaflet 1.9.5" pasaria groundedness
si el chunk trae un `1.9` y un `5` en cualquier parte — un **falso positivo**, que es peor
que un falso negativo: publica como fundamentado algo que no lo esta.

**Regla 3 — un identificador se compara entero.** `MIL-PRF-14107` se compara asi, no como
`PRF-14107`.

**Regla 4 — un numero que enumera no es un numero que afirma.** En "1) Notificar. 2) Abrir
QS-1." los `1` y `2` son marcadores de lista, no datos. Extraerlos hacia que un sistema que
numera sus pasos fallara groundedness por numerar — otro falso negativo que manda a
arreglar un sistema sano. (Encontrado al llenar el reporte de M4 con el caso del LOTO.)

**Regla 5 — la ambiguedad de `1.200` se documenta, no se adivina en silencio.** En espanol
es mil doscientos; en ingles, uno punto dos. La convencion esta en `canonicalize`, con
test, y cada check guarda **el token crudo junto al canonico** para poder auditar
cualquier desacuerdo sin leer el codigo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Un token es una corrida de alfanumericos unida por separadores internos. Se clasifica
# despues; no se intenta distinguir numero de identificador con la regex, porque ahi es
# donde se cuelan los casos raros.
_TOKEN = re.compile(r"[A-Za-z0-9]+(?:[.,\-/][A-Za-z0-9]+)*")
_SEPARATORS = ".,-/"

# Marcador de lista: un numero suelto seguido de `)` o de `.` mas espacio, ya sea al
# principio de una linea o detras de un parentesis/espacio. Implementa la regla 4.
_ENUMERATOR = re.compile(r"(?:^|[\s(\[])\d{1,2}[.)](?=\s|$)", re.MULTILINE)


@dataclass(frozen=True)
class NumberToken:
    raw: str
    canonical: str

    def __str__(self) -> str:  # pragma: no cover - conveniencia de debug
        return f"{self.raw}→{self.canonical}"


def _split_groups(token: str) -> tuple[list[str], list[str]]:
    """Separa un token en grupos y en los separadores que los unen."""
    grupos, seps, actual = [], [], ""
    for ch in token:
        if ch in _SEPARATORS:
            grupos.append(actual)
            seps.append(ch)
            actual = ""
        else:
            actual += ch
    grupos.append(actual)
    return grupos, seps


def is_number(token: str) -> bool:
    """El token es un numero, y no un identificador?

    Implementa las reglas 1 y 2. Los casos limite estan cubiertos por tests con nombre.
    """
    grupos, seps = _split_groups(token)
    if any(not g.isdigit() for g in grupos):
        return False                      # tiene letras -> identificador (regla 1)
    if len(seps) == 0:
        return True                       # 720
    if len(seps) == 1:
        return True                       # 68,5 · 1.200 -> lo resuelve canonicalize
    # Tres o mas grupos (regla 2): solo es numero si se ve como miles + decimal.
    if set(seps) in ({".", ","}, {",", "."}):
        return True                       # 1.200,50 · 1,200.50
    if seps[0] in "-/":
        return False                      # 9150-00-292-9689 · 12/07/2024
    # Mismo separador repetido: numero solo si todos los grupos menos el primero son de
    # 3 digitos (1.200.000). Si no, es una version: 1.9.4
    return all(len(g) == 3 for g in grupos[1:])


def canonicalize(raw: str) -> str:
    """Forma canonica de un numero escrito.

    Convencion, elegida y fijada con test:
    - Si aparecen `.` y `,` en el mismo token, **el ultimo es el decimal**
      (`1.200,50` → `1200.50`). No tiene ambiguedad.
    - Un solo separador **seguido por exactamente 3 digitos** se lee como separador de
      miles (`1.200` → `1200`).
      ⚠️ **Limitacion conocida y aceptada:** `68.500` se lee `68500`, no 68.5 con ceros de
      relleno. En documentacion tecnica el separador de miles es mucho mas frecuente que
      tres decimales, y adivinar por contexto seria menos predecible. El token crudo
      queda guardado para auditarlo.
    - Cualquier otro separador unico es decimal (`68,5` → `68.5`).
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


def _enumerator_spans(text: str) -> list[tuple[int, int]]:
    return [m.span() for m in _ENUMERATOR.finditer(text)]


def _tokens(text: str | None) -> list[str]:
    if not text:
        return []
    enumeradores = _enumerator_spans(text)
    out = []
    for m in _TOKEN.finditer(text):
        if not any(ch.isdigit() for ch in m.group(0)):
            # Un token sin digitos no interesa a este modulo: es una palabra.
            continue
        if any(ini <= m.start() and m.end() <= fin for ini, fin in enumeradores):
            continue    # marcador de lista (regla 4)
        out.append(m.group(0))
    return out


def extract_numbers(text: str | None) -> list[NumberToken]:
    return [
        NumberToken(raw=t, canonical=canonicalize(t)) for t in _tokens(text) if is_number(t)
    ]


def extract_codes(text: str | None) -> list[str]:
    """Identificadores tecnicos, enteros y en mayusculas: `E-114`, `M24`, `MIL-PRF-14107`,
    `9150-00-292-9689`, `1.9.4`."""
    return [t.upper() for t in _tokens(text) if not is_number(t)]


def contains_number(haystack: str | None, needle: str) -> bool:
    """`needle` aparece en `haystack`, comparando en forma canonica.

    Canonico contra canonico y no substring crudo a proposito: buscar "30" como substring
    lo encontraria dentro de "1300", dando por fundamentado un numero que nunca estuvo.
    """
    objetivo = canonicalize(needle)
    return any(tok.canonical == objetivo for tok in extract_numbers(haystack))


def contains_code(haystack: str | None, needle: str) -> bool:
    return needle.upper() in extract_codes(haystack)
