"""Non-invasive execution telemetry for the Stage-6 legacy controller.

The observer is intentionally optional. When no observer is attached, emitting an
execution event is a no-op and must not change controller behavior or environment
step counts.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, MutableSequence, Optional, Protocol, Tuple, runtime_checkable


OBSERVER_ATTRIBUTE = "_dc3pa_execution_observer"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_copy(value: Any) -> Any:
    """Best-effort copy without imposing JSON conversion on RGB arrays."""
    try:
        return deepcopy(value)
    except Exception:
        return value


@dataclass(frozen=True)
class ExecutionEvent:
    event_type: str
    timestamp_utc: str
    plan_id: str = ""
    plan_version: int = 0
    step_id: str = ""
    step_index: int = -1
    action_index: int = -1
    status: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, include_payload: bool = True) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "event_type": self.event_type,
            "timestamp_utc": self.timestamp_utc,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "step_id": self.step_id,
            "step_index": self.step_index,
            "action_index": self.action_index,
            "status": self.status,
        }
        if include_payload:
            data["payload"] = dict(self.payload)
        return data


@runtime_checkable
class ExecutionObserver(Protocol):
    def emit(self, event: ExecutionEvent) -> None:
        ...

    def clear(self) -> None:
        ...

    def finalize_workflow(self, *, success: bool, reason: str = "") -> None:
        ...

    def events(self) -> Tuple[ExecutionEvent, ...]:
        ...


class NullExecutionObserver:
    def emit(self, event: ExecutionEvent) -> None:
        del event

    def clear(self) -> None:
        return None

    def finalize_workflow(self, *, success: bool, reason: str = "") -> None:
        del success, reason

    def events(self) -> Tuple[ExecutionEvent, ...]:
        return ()


class InMemoryExecutionObserver:
    """Simple event collector used by tests, calibration logs, and acquisition."""

    def __init__(self) -> None:
        self._events: MutableSequence[ExecutionEvent] = []
        self._workflow_finished = False

    def emit(self, event: ExecutionEvent) -> None:
        self._events.append(event)
        if event.event_type == "workflow_finished":
            self._workflow_finished = True

    def clear(self) -> None:
        self._events.clear()
        self._workflow_finished = False

    def finalize_workflow(self, *, success: bool, reason: str = "") -> None:
        if self._workflow_finished:
            return
        self.emit(
            make_execution_event(
                "workflow_finished",
                status="success" if success else "failure",
                reason=reason,
            )
        )

    def events(self) -> Tuple[ExecutionEvent, ...]:
        return tuple(self._events)



def make_execution_event(
    event_type: str,
    *,
    plan_id: str = "",
    plan_version: int = 0,
    step_id: str = "",
    step_index: int = -1,
    action_index: int = -1,
    status: str = "",
    **payload: Any,
) -> ExecutionEvent:
    return ExecutionEvent(
        event_type=str(event_type),
        timestamp_utc=_utc_now(),
        plan_id=str(plan_id or ""),
        plan_version=int(plan_version or 0),
        step_id=str(step_id or ""),
        step_index=int(step_index),
        action_index=int(action_index),
        status=str(status or ""),
        payload={key: _safe_copy(value) for key, value in payload.items()},
    )


def get_execution_observer(target: Any) -> Optional[ExecutionObserver]:
    observer = getattr(target, OBSERVER_ATTRIBUTE, None)
    if observer is None:
        return None
    if not isinstance(observer, ExecutionObserver):
        # Structural Protocol checks can fail for custom minimal observers. Fall
        # back to checking the only required hot-path method.
        if not callable(getattr(observer, "emit", None)):
            return None
    return observer


def emit_execution_event(target: Any, event_type: str, **kwargs: Any) -> None:
    """Emit without ever allowing telemetry failure to break task execution."""
    observer = get_execution_observer(target)
    if observer is None:
        return
    try:
        observer.emit(make_execution_event(event_type, **kwargs))
    except Exception:
        # Telemetry is auxiliary. Failure handling is intentionally fail-open here;
        # the runtime may separately record an observer error in its trace.
        return


def snapshot_inventory(memory: Any) -> Dict[str, Any]:
    inventory = getattr(memory, "inventory", {}) if memory is not None else {}
    if isinstance(inventory, Mapping):
        return {str(key): _safe_copy(value) for key, value in inventory.items()}
    return {}


def current_rgb_from_events(events: Any) -> Any:
    """Return an already-observed RGB frame; never calls env.step()."""
    if isinstance(events, Mapping):
        return events.get("rgb")
    return None


def compact_action_payload(action: Any) -> Dict[str, Any]:
    if isinstance(action, Mapping):
        return {str(key): _safe_copy(value) for key, value in action.items()}
    return {"raw_action": _safe_copy(action)}
