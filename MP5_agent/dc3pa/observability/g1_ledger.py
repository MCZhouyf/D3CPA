"""Credential-safe logical-call/relay-attempt ledger for G1."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from .trace import JsonlTraceWriter


def _hash_request(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> str:
    # The raw prompt is never persisted; only a stable content hash is retained.
    material = repr((args, sorted(kwargs))).encode("utf-8", errors="replace")
    return hashlib.sha256(material).hexdigest()


def _usage(result: Any) -> tuple[int | None, int | None, int | None, str]:
    metadata = getattr(result, "usage_metadata", None) or getattr(result, "response_metadata", {}).get("token_usage", {})
    if not isinstance(metadata, Mapping):
        return None, None, None, "unavailable"
    prompt = metadata.get("input_tokens", metadata.get("prompt_tokens"))
    completion = metadata.get("output_tokens", metadata.get("completion_tokens"))
    total = metadata.get("total_tokens")
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in (prompt, completion, total)):
        return None, None, None, "unavailable"
    return prompt, completion, total, "api_usage"


def _estimate_tokens(value: Any) -> int:
    """Stable local fallback, intentionally computed but never persisted verbatim.

    The relay used for G1 does not provide provider token-usage fields.  A
    conservative four-Unicode-character approximation lets throughput reports
    remain numeric without retaining a prompt or completion in the ledger.
    """

    text = repr(value)
    return max(1, (len(text) + 3) // 4)


def _estimated_usage(args: tuple[Any, ...], kwargs: Mapping[str, Any], result: Any) -> tuple[int, int, int]:
    prompt = _estimate_tokens((args, sorted(kwargs.items())))
    completion = _estimate_tokens(getattr(result, "content", result))
    return prompt, completion, prompt + completion


class LedgerChatModel:
    """Proxy that observes calls without modifying request/response semantics."""

    def __init__(self, model: Any, path: str | Path, *, context: Mapping[str, Any]) -> None:
        self._model = model
        self._writer = JsonlTraceWriter(path)
        self._context = dict(context)

    def _call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        logical_call_id = uuid.uuid4().hex
        started = time.perf_counter()
        base = {**self._context, "logical_call_id": logical_call_id, "caller_type": self._context.get("caller_type", "other"),
                "relay_request_id": None, "retry_idx": 0, "request_payload_hash": _hash_request(args, kwargs)}
        self._writer.write("llm_logical_call_started", {**base, "method": method_name})
        try:
            result = getattr(self._model, method_name)(*args, **kwargs)
        except Exception as exc:
            self._writer.write("llm_relay_attempt", {**base, "status": "failure", "error_type": type(exc).__name__, "latency_ms": round((time.perf_counter() - started) * 1000, 3), "prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "token_count_source": "unavailable"})
            raise
        prompt, completion, total, source = _usage(result)
        if source == "unavailable":
            prompt, completion, total = _estimated_usage(args, kwargs, result)
            source = "estimated"
        self._writer.write("llm_relay_attempt", {**base, "status": "success", "error_type": None, "latency_ms": round((time.perf_counter() - started) * 1000, 3), "prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total, "token_count_source": source})
        return result

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("__call__", *args, **kwargs)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("invoke", *args, **kwargs)

    def predict(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("predict", *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._model, name)
