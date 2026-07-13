"""JSON-safe execution telemetry persistence.

ExecutionObserver payloads may contain RGB arrays and simulator-specific objects.
Calibration needs action, result, inventory, and failure metadata, but it must not
inline large image tensors into every episode JSON.  This module strips binary/
array image fields while preserving the rest of the event payload.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence


_IMAGE_KEYS = {
    "rgb",
    "image",
    "frame",
    "pixels",
    "observation_image",
}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            pass
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            pass
    return repr(value)


def sanitize_payload(
    payload: Mapping[str, Any],
    *,
    image_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Remove inline image tensors and return a JSON-safe payload copy."""

    result: MutableMapping[str, Any] = {}
    for key, value in payload.items():
        if str(key).lower() in _IMAGE_KEYS:
            continue
        result[str(key)] = _json_safe(value)
    if image_path:
        result["image_path"] = str(image_path)
    return dict(result)


def serialize_execution_event(
    event: Any,
    *,
    image_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Serialize an ExecutionEvent-like object with a cleaned payload.

    The function deliberately uses duck typing so it remains compatible with
    minimal test doubles and the Round-1 ``ExecutionEvent`` dataclass.
    """

    if hasattr(event, "to_dict") and callable(event.to_dict):
        try:
            raw = event.to_dict(include_payload=True)
        except TypeError:
            raw = event.to_dict()
    elif isinstance(event, Mapping):
        raw = deepcopy(dict(event))
    else:
        raw = {
            "event_type": getattr(event, "event_type", ""),
            "timestamp_utc": getattr(event, "timestamp_utc", ""),
            "plan_id": getattr(event, "plan_id", ""),
            "plan_version": getattr(event, "plan_version", 0),
            "step_id": getattr(event, "step_id", ""),
            "step_index": getattr(event, "step_index", -1),
            "action_index": getattr(event, "action_index", -1),
            "status": getattr(event, "status", ""),
            "payload": getattr(event, "payload", {}),
        }

    payload = raw.get("payload", {})
    raw["payload"] = sanitize_payload(
        payload if isinstance(payload, Mapping) else {}, image_path=image_path
    )
    return _json_safe(raw)
