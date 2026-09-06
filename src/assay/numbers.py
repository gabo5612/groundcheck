"""Extraction of numbers and identifiers from an answer's text.

This module decides whether `grounded` returns true or false, so its rules are written out
explicitly. The first three came from **actually trying to label the golden set (M3) and
watching it fail**, not from imagining cases:

**Rule 1 — a digit glued to a letter is not a number, it is an identifier.**
`E-114` does not contribute the number 114, nor `M24` the 24. Extracting them as numbers
would make the *correct* answer "alarm E-114 indicates overtemperature" return
`grounded: false` because "114" never appears loose in the chunk. That false negative sends
you to fix a healthy system.

**Rule 2 — a token with three or more separated groups is an identifier, not several
numbers.** `1.9.4` is not "1.9 and 4", and `9150-00-292-9689` (an NSN) is not anything cut
into pieces. Without this rule, a system answering "Leaflet 1.9.5" would pass groundedness
if the chunk contains a `1.9` and a `5` anywhere — a **false positive**, which is worse than
a false negative: it publishes as grounded something that is not.

**Rule 3 — an identifier is compared whole.** `MIL-PRF-14107` is compared as such, not as
`PRF-14107`.

**Rule 4 — a number that enumerates is not a number that asserts.** In "1) Notify. 2) Open
QS-1." the `1` and `2` are list markers, not data. Extracting them made a system that
numbers its steps fail groundedness *for numbering* — another false negative sending you to
fix a healthy system. (Found while filling in the M4 report with the LOTO case.)

**Rule 4b — a citation marker is not data.** In "720 +/- 30 N.m [1]" the `[1]` is a
reference to the passage, not a magnitude. Demanding it be grounded in the chunk fails a
system **for citing properly**, which is the behaviour the harness rewards in every other
check. (Found on the first run against the real anvil, which cites with `[n]`: without this
rule its measured groundedness was 0.18 while the answers were correct.)

**Rule 5 — the ambiguity of `1.200` is documented, not silently guessed.** In Spanish it is
one thousand two hundred; in English, one point two. The convention lives in `canonicalize`,
with a test, and every check stores **the raw token alongside the canonical one** so any
disagreement can be audited without reading the code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A token is a run of alphanumerics joined by internal separators. Classification happens
# afterwards; the regex does not try to tell a number from an identifier, because that is
# exactly where the odd cases slip through.
_TOKEN = re.compile(r"[A-Za-z0-9]+(?:[.,\-/:][A-Za-z0-9]+)*")
_SEPARATORS = ".,-/:"

# List marker: a bare number followed by `)` or `.` plus a space, either at the start of a
# line or after a parenthesis/space. Implements rule 4.
_ENUMERATOR = re.compile(r"(?:^|[\s(\[])\d{1,2}[.)](?=\s|$)", re.MULTILINE)

# Citation marker: [1] · [12] · [1,2] · [1-3]. Implements rule 4b.
_CITATION_MARK = re.compile(r"\[\s*\d{1,3}(?:\s*[,;-]\s*\d{1,3})*\s*\]")


@dataclass(frozen=True)
class NumberToken:
    raw: str
    canonical: str

    def __str__(self) -> str:  # pragma: no cover - debugging convenience
        return f"{self.raw}→{self.canonical}"


def _split_groups(token: str) -> tuple[list[str], list[str]]:
    """Split a token into its groups and the separators joining them."""
    groups, seps, current = [], [], ""
    for ch in token:
        if ch in _SEPARATORS:
            groups.append(current)
            seps.append(ch)
            current = ""
        else:
            current += ch
    groups.append(current)
    return groups, seps


def is_number(token: str) -> bool:
    """Is this token a number rather than an identifier?

    Implements rules 1 and 2. The edge cases are covered by named tests.
    """
    groups, seps = _split_groups(token)
    if any(not g.isdigit() for g in groups):
        return False                      # has letters -> identifier (rule 1)
    if len(seps) == 0:
        return True                       # 720
    if len(seps) == 1:
        return seps[0] != ":"             # 68,5 · 1.200 -> canonicalize resolves it
    # Three or more groups (rule 2): a number only if it looks like thousands + decimal.
    if set(seps) in ({".", ","}, {",", "."}):
        return True                       # 1.200,50 · 1,200.50
    if ":" in seps:
        return False                      # 09:00 — a time is a value, not a magnitude
    if seps[0] in "-/":
        return False                      # 9150-00-292-9689 · 12/07/2024
    # Same separator repeated: a number only if every group but the first has 3 digits
    # (1.200.000). Otherwise it is a version: 1.9.4
    return all(len(g) == 3 for g in groups[1:])


def canonicalize(raw: str) -> str:
    """Canonical form of a written number.

    The convention, chosen and pinned by tests:
    - If `.` and `,` both appear in the same token, **the last one is the decimal**
      (`1.200,50` → `1200.50`). No ambiguity there.
    - A single separator **followed by exactly 3 digits** reads as a thousands separator
      (`1.200` → `1200`).
      ⚠️ **Known and accepted limitation:** `68.500` reads as `68500`, not 68.5 with padding
      zeros. In technical documentation the thousands separator is far more common than
      three decimals, and guessing from context would be less predictable. The raw token is
      stored so it can be audited.
    - Any other single separator is a decimal (`68,5` → `68.5`).
    - Trailing zeros on a decimal are trimmed (`680.0` → `680`) so that `680` and `680.0`
      do not count as different numbers.
    """
    token = raw.replace(" ", "").replace(" ", "")

    if "." in token and "," in token:
        decimal_sep = "." if token.rfind(".") > token.rfind(",") else ","
        thousands_sep = "," if decimal_sep == "." else "."
        token = token.replace(thousands_sep, "").replace(decimal_sep, ".")
    else:
        for sep in (".", ","):
            if sep in token:
                head, _, tail = token.rpartition(sep)
                if len(tail) == 3 and head.replace(sep, "").isdigit():
                    token = token.replace(sep, "")       # thousands separator
                else:
                    token = token.replace(sep, ".")      # decimal
                break

    if "." in token:
        token = token.rstrip("0").rstrip(".")
    return token or "0"


def _skip_spans(text: str) -> list[tuple[int, int]]:
    """Spans that carry no data: list markers and citation markers."""
    return [m.span() for m in _ENUMERATOR.finditer(text)] + [
        m.span() for m in _CITATION_MARK.finditer(text)
    ]


def _split_unit(token: str) -> list[str]:
    """Separate a value from its unit when `/` joins them.

    `149.99/year` is a price with a unit, not an identifier: without this split the whole
    token classifies as an identifier (because "year" is letters) and the 149.99 is never
    compared against anything. Same for `USD/lb` or `5.56/mm`.

    A `/` between groups that BOTH carry digits does join: `12/07/2024` stays one whole
    date, not three loose numbers.
    """
    if "/" not in token:
        return [token]
    parts = token.split("/")
    if all(any(ch.isdigit() for ch in p) for p in parts):
        return [token]        # 12/07/2024 — kept whole
    return [p for p in parts if any(ch.isdigit() for ch in p)]


def _tokens(text: str | None) -> list[str]:
    if not text:
        return []
    skip = _skip_spans(text)
    out = []
    for m in _TOKEN.finditer(text):
        if not any(ch.isdigit() for ch in m.group(0)):
            # A token with no digits is of no interest here: it is a word.
            continue
        if any(start <= m.start() and m.end() <= end for start, end in skip):
            continue    # list or citation marker (rules 4 and 4b)
        out.extend(_split_unit(m.group(0)))
    return out


def extract_numbers(text: str | None) -> list[NumberToken]:
    return [
        NumberToken(raw=t, canonical=canonicalize(t)) for t in _tokens(text) if is_number(t)
    ]


def extract_codes(text: str | None) -> list[str]:
    """Technical identifiers, whole and uppercased: `E-114`, `M24`, `MIL-PRF-14107`,
    `9150-00-292-9689`, `1.9.4`."""
    return [t.upper() for t in _tokens(text) if not is_number(t)]


def contains_number(haystack: str | None, needle: str) -> bool:
    """Whether `needle` appears in `haystack`, compared in canonical form.

    Canonical against canonical rather than raw substring, on purpose: searching for "30"
    as a substring would find it inside "1300", declaring grounded a number that was never
    there.
    """
    target = canonicalize(needle)
    return any(tok.canonical == target for tok in extract_numbers(haystack))


def contains_code(haystack: str | None, needle: str) -> bool:
    return needle.upper() in extract_codes(haystack)
