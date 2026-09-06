"""Adapters to the system under test.

The contract is one thing only: `question -> {answer, citations[], abstained}`. `groundcheck`
knows nothing about any RAG's internals, and that is what makes it usable against all of
them — publishable rather than an internal utility.
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
    """A fake system scripted from a file.

    On purpose it does **not** answer well by itself. The answers come from a hand-written
    file, so the harness's tests are deterministic and so the "answered with an invented
    number" case can be constructed at will. A mock that answered correctly by deriving
    from the golden set itself would prove nothing: it would measure the mock.
    """

    kind = "mock"

    def __init__(self, path: str | Path):
        self.target = str(path)
        doc = yaml.safe_load(Path(path).read_text("utf-8")) or {}
        responses = doc.get("responses") if isinstance(doc, dict) else doc
        if not isinstance(responses, dict):
            raise ValueError(f"{path}: expected a map `responses: {{question: ...}}`")
        self._by_question: dict[str, dict[str, Any]] = responses
        self._default = doc.get("default") if isinstance(doc, dict) else None

    def ask(self, question: str) -> Response:
        raw = self._by_question.get(question, self._default)
        if raw is None:
            # Explicit silence: the mock has no script for this question. It is recorded
            # as an abstention rather than blowing up, so a new suite still runs.
            return Response(answer=None, abstained=True, latency_ms=0)
        return Response(
            answer=raw.get("answer"),
            citations=tuple(raw.get("citations") or ()),
            retrieved=tuple(raw.get("retrieved") or ()),
            abstained=bool(raw.get("abstained", raw.get("answer") is None)),
            latency_ms=0,
            extra=(("reason", raw["reason"]),) if "reason" in raw else (),
        )


def _remap(raw: Any, item_map: dict[str, str]) -> dict[str, Any]:
    """Renames an item's keys according to the mapping. Unmapped keys are preserved."""
    if not isinstance(raw, dict):
        return {"raw": raw}
    out = dict(raw)
    for destino, origen in item_map.items():
        if origen in raw:
            out[destino] = raw[origen]
    return out


class HttpAdapter:
    """Any endpoint accepting JSON `{"question": ...}` and returning the contract.

    Field names are configurable because there is no standard and pretending otherwise
    helps no one: whoever integrates their system maps their keys and moves on.
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
        retrieved_field: str = "retrieved",
        abstained_field: str = "abstained",
        item_map: dict[str, str] | None = None,
        extra_request: dict[str, Any] | None = None,
        passthrough: list[str] | None = None,
    ):
        self.target = url
        self._timeout = timeout
        self._qf = question_field
        self._af = answer_field
        self._cf = citations_field
        self._rf = retrieved_field
        self._absf = abstained_field
        self._item_map = item_map or {}
        self._extra = extra_request or {}
        self._passthrough = tuple(passthrough or ())

    def ask(self, question: str) -> Response:
        payload = json.dumps({self._qf: question, **self._extra}).encode("utf-8")
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
            raise ValueError(f"the system returned {type(body).__name__}, expected a JSON object")

        answer = body.get(self._af)
        citations = body.get(self._cf) or []
        if not isinstance(citations, list):
            raise ValueError(f"`{self._cf}` should be a list, got {type(citations).__name__}")
        # If the system does not report abstention explicitly, it is inferred from the
        # absence of an answer. Noted here because the abstention rate is the most
        # important metric in the set and it matters whether it came declared or inferred.
        retrieved = body.get(self._rf) or []
        if not isinstance(retrieved, list):
            raise ValueError(f"`{self._rf}` should be a list, got {type(retrieved).__name__}")

        abstained = body.get(self._absf)
        if abstained is None:
            abstained = answer is None or (isinstance(answer, str) and not answer.strip())

        return Response(
            answer=answer,
            citations=tuple(_remap(c, self._item_map) for c in citations),
            retrieved=tuple(_remap(r, self._item_map) for r in retrieved),
            abstained=bool(abstained),
            latency_ms=latency_ms,
            extra=tuple((k, body[k]) for k in self._passthrough if k in body),
        )


def build_adapter(
    spec: str, *, timeout: float = 60.0, mapping: str | Path | None = None
) -> Adapter:
    """`mock:path.yaml` -> MockAdapter · `http(s)://...` -> HttpAdapter.

    `mapping` is a YAML describing how to translate the system's response onto the
    contract. Everything system-specific lives there and not in the harness's code.
    """
    if spec.startswith("mock:"):
        return MockAdapter(spec[len("mock:") :])
    if not spec.startswith(("http://", "https://")):
        raise ValueError(f"unrecognised --system: {spec!r} (use `mock:file.yaml` or an http URL)")

    kw: dict[str, Any] = {}
    if mapping is not None:
        doc = yaml.safe_load(Path(mapping).read_text("utf-8")) or {}
        req = doc.get("request") or {}
        resp = doc.get("response") or {}
        kw = {
            "question_field": req.get("question_field", "question"),
            "extra_request": req.get("extra") or {},
            "answer_field": resp.get("answer_field", "answer"),
            "citations_field": resp.get("citations_field", "citations"),
            "retrieved_field": resp.get("retrieved_field", "retrieved"),
            "abstained_field": resp.get("abstained_field", "abstained"),
            "item_map": resp.get("item_map") or {},
            "passthrough": resp.get("passthrough") or [],
        }
    return HttpAdapter(spec, timeout=timeout, **kw)
