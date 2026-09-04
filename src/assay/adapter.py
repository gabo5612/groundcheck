"""Adaptadores al sistema bajo prueba.

El contrato es una sola cosa: `pregunta -> {answer, citations[], abstained}`. `assay` no
sabe nada de `anvil` por dentro, y por eso sirve para medir cualquier RAG — es lo que lo
hace publicable y no una utilidad interna.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

import yaml

from .schema import Response


class Adapter(Protocol):
    kind: str
    target: str

    def ask(self, question: str) -> Response: ...


class MockAdapter:
    """Sistema falso guionado desde un archivo.

    A proposito **no** responde bien solo. Las respuestas salen de un archivo escrito a
    mano, para que los tests del harness sean deterministas y para poder construir a
    voluntad el caso "respondio con un numero inventado". Un mock que contestara
    correctamente derivando del propio golden set no probaria nada: mediria al mock.
    """

    kind = "mock"

    def __init__(self, path: str | Path):
        self.target = str(path)
        doc = yaml.safe_load(Path(path).read_text("utf-8")) or {}
        responses = doc.get("responses") if isinstance(doc, dict) else doc
        if not isinstance(responses, dict):
            raise ValueError(f"{path}: se esperaba un mapa `responses: {{pregunta: ...}}`")
        self._by_question: dict[str, dict[str, Any]] = responses
        self._default = doc.get("default") if isinstance(doc, dict) else None

    def ask(self, question: str) -> Response:
        raw = self._by_question.get(question, self._default)
        if raw is None:
            # Silencio explicito: el mock no tiene guion para esta pregunta. Se registra
            # como abstencion en vez de reventar, para que una suite nueva corra igual.
            return Response(answer=None, abstained=True, latency_ms=0)
        return Response(
            answer=raw.get("answer"),
            citations=tuple(raw.get("citations") or ()),
            abstained=bool(raw.get("abstained", raw.get("answer") is None)),
            latency_ms=0,
        )


class HttpAdapter:
    """Cualquier endpoint que acepte JSON `{"question": ...}` y devuelva el contrato.

    Los nombres de campo son configurables porque no hay un estandar y no vale la pena
    fingir que lo hay: el que integra su sistema mapea sus claves y sigue.
    """

    kind = "http"

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 60.0,
        question_field: str = "question",
        answer_field: str = "answer",
        citations_field: str = "citations",
        abstained_field: str = "abstained",
    ):
        self.target = url
        self._timeout = timeout
        self._qf = question_field
        self._af = answer_field
        self._cf = citations_field
        self._absf = abstained_field

    def ask(self, question: str) -> Response:
        payload = json.dumps({self._qf: question}).encode("utf-8")
        req = urllib.request.Request(
            self.target,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        latency_ms = int((time.perf_counter() - started) * 1000)

        if not isinstance(body, dict):
            raise ValueError(f"el sistema devolvio {type(body).__name__}, se esperaba un objeto JSON")

        answer = body.get(self._af)
        citations = body.get(self._cf) or []
        if not isinstance(citations, list):
            raise ValueError(f"`{self._cf}` deberia ser una lista, vino {type(citations).__name__}")
        # Si el sistema no reporta abstencion explicita, se infiere de la ausencia de
        # respuesta. Se deja anotado porque la tasa de abstencion es la metrica mas
        # importante del set y conviene saber si vino declarada o inferida.
        abstained = body.get(self._absf)
        if abstained is None:
            abstained = answer is None or (isinstance(answer, str) and not answer.strip())

        return Response(
            answer=answer,
            citations=tuple(c if isinstance(c, dict) else {"raw": c} for c in citations),
            abstained=bool(abstained),
            latency_ms=latency_ms,
        )


def build_adapter(spec: str, *, timeout: float = 60.0) -> Adapter:
    """`mock:ruta.yaml` -> MockAdapter · `http(s)://...` -> HttpAdapter."""
    if spec.startswith("mock:"):
        return MockAdapter(spec[len("mock:") :])
    if spec.startswith(("http://", "https://")):
        return HttpAdapter(spec, timeout=timeout)
    raise ValueError(f"--system no reconocido: {spec!r} (usa `mock:archivo.yaml` o una URL http)")
