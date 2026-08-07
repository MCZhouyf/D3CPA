"""Credential-safe logical-call/relay-attempt ledger for G1."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from .trace import JsonlTraceWriter


_RELAY_LOCK = threading.Lock()
_NEXT_RELAY_AT = 0.0


def _reserve_relay_slot(min_interval_seconds: float) -> None:
    """Serialize G1 relay submissions across Planner and Reflection wrappers."""
    global _NEXT_RELAY_AT
    with _RELAY_LOCK:
        now = time.monotonic()
        delay = max(0.0, _NEXT_RELAY_AT - now)
        _NEXT_RELAY_AT = max(_NEXT_RELAY_AT, now) + min_interval_seconds
    if delay:
        time.sleep(delay)


def _is_rate_limit(exc: Exception) -> bool:
    return type(exc).__name__ == "RateLimitError" or "429" in str(exc)


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


class LedgerChatModel:
    """Proxy that observes calls without modifying request/response semantics."""

    def __init__(self, model: Any, path: str | Path, *, context: Mapping[str, Any], min_relay_interval_seconds: float = 15.0, max_rate_limit_retries: int = 3, rate_limit_backoff_seconds: float = 30.0, request_timeout_seconds: float | None = None) -> None:
        self._model = model
        self._writer = JsonlTraceWriter(path)
        self._context = dict(context)
        self._min_relay_interval_seconds = float(min_relay_interval_seconds)
        self._max_rate_limit_retries = int(max_rate_limit_retries)
        self._rate_limit_backoff_seconds = float(rate_limit_backoff_seconds)
        configured_timeout = os.environ.get("DC3PA_LLM_REQUEST_TIMEOUT", "")
        self._request_timeout_seconds = float(
            configured_timeout if request_timeout_seconds is None else request_timeout_seconds
        ) if (configured_timeout or request_timeout_seconds is not None) else 0.0
        if self._request_timeout_seconds < 0:
            raise ValueError("request_timeout_seconds must be non-negative")

    def _invoke_with_hard_timeout(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Bound an old relay client's blocking call in the G1 subprocess.

        ``request_timeout`` is not consistently honored by the pinned client
        version.  SIGALRM interrupts the blocking request without spawning a
        background thread, so a timeout cannot create concurrent relay calls.
        """
        callback = getattr(self._model, method_name)
        timeout = self._request_timeout_seconds
        if (
            timeout <= 0
            or threading.current_thread() is not threading.main_thread()
            or not hasattr(signal, "setitimer")
        ):
            return callback(*args, **kwargs)
        active_timer, active_interval = signal.getitimer(signal.ITIMER_REAL)
        previous_handler = signal.getsignal(signal.SIGALRM)

        def _raise_timeout(_signum: int, _frame: Any) -> None:
            raise TimeoutError(f"G1 LLM request exceeded {timeout:g} seconds")

        # A surrounding library can already own ITIMER_REAL.  The previous
        # implementation bypassed the request timeout in that situation,
        # leaving a relay read unbounded.  Preserve the earlier deadline by
        # using the shorter of the two timers, then restore its remaining
        # duration after this call exits.
        effective_timeout = min(timeout, active_timer) if active_timer > 0 else timeout
        started = time.monotonic()
        signal.signal(signal.SIGALRM, _raise_timeout)
        signal.setitimer(signal.ITIMER_REAL, effective_timeout)
        try:
            return callback(*args, **kwargs)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
            if active_timer > 0:
                remaining = max(0.0, active_timer - (time.monotonic() - started))
                signal.setitimer(signal.ITIMER_REAL, remaining, active_interval)

    def _call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        logical_call_id = uuid.uuid4().hex
        base = {**self._context, "logical_call_id": logical_call_id, "caller_type": self._context.get("caller_type", "other"),
                "relay_request_id": None, "request_payload_hash": _hash_request(args, kwargs),
                "request_timeout_seconds": self._request_timeout_seconds or None}
        self._writer.write("llm_logical_call_started", {**base, "method": method_name})
        for retry_idx in range(self._max_rate_limit_retries + 1):
            _reserve_relay_slot(self._min_relay_interval_seconds)
            started = time.perf_counter()
            try:
                result = self._invoke_with_hard_timeout(method_name, *args, **kwargs)
            except Exception as exc:
                self._writer.write("llm_relay_attempt", {**base, "retry_idx": retry_idx, "status": "failure", "error_type": type(exc).__name__, "latency_ms": round((time.perf_counter() - started) * 1000, 3), "prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "token_count_source": "unavailable"})
                if not _is_rate_limit(exc) or retry_idx >= self._max_rate_limit_retries:
                    raise
                time.sleep(self._rate_limit_backoff_seconds * (2 ** retry_idx))
                continue
            prompt, completion, total, source = _usage(result)
            self._writer.write("llm_relay_attempt", {**base, "retry_idx": retry_idx, "status": "success", "error_type": None, "latency_ms": round((time.perf_counter() - started) * 1000, 3), "prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total, "token_count_source": source})
            return result
        raise RuntimeError("unreachable relay retry state")

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("__call__", *args, **kwargs)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("invoke", *args, **kwargs)

    def predict(self, *args: Any, **kwargs: Any) -> Any:
        return self._call("predict", *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._model, name)
