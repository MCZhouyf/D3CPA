"""Non-invasive recorder for every direct inventory write.

Stage A needs an exact, auditable record of the scripted low-level execution
substitute: when it fires, for which task, which items it grants, and how often
each runtime mode invokes it.

This module does NOT modify any file under ``MP5_agent/agent/`` or
``MP5_agent/dc3pa/``. It wraps the MineDojo environment object's
``set_inventory`` bound method at episode construction time and restores it on
close. Behaviour is unchanged: the original method is always called with the
original arguments, and its return value is passed through untouched.

Usage (in the run script only, not in base code)::

    from dc3pa_stage_a.inventory_write_logger import InventoryWriteLogger

    env = minedojo.make(...)
    logger = InventoryWriteLogger(
        jsonl_path=f"runs/{run_id}/inventory_writes.jsonl",
        context={
            "run_id": run_id,
            "task": task_name,
            "seed": episode_seed,
            "runtime_mode": cfg.mode,
            "memory_mode": cfg.memory_mode,
            "legacy_task_hacks": os.environ.get("DC3PA_LEGACY_TASK_HACKS"),
            "bounded_resource_fallback": os.environ.get(
                "DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK"
            ),
        },
    )
    logger.install(env)
    try:
        ...run the episode...
    finally:
        logger.uninstall()
"""

from __future__ import annotations

import inspect
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _item_to_mapping(item: Any) -> Dict[str, Any]:
    """Normalise a MineDojo ``InventoryItem`` (or anything duck-typed) to a dict."""
    if isinstance(item, Mapping):
        raw = dict(item)
    else:
        raw = {
            field: getattr(item, field, None)
            for field in ("slot", "name", "variant", "quantity")
        }
    name = raw.get("name")
    quantity = raw.get("quantity")
    try:
        quantity = int(quantity) if quantity is not None else None
    except (TypeError, ValueError):
        quantity = None
    return {
        "slot": raw.get("slot"),
        "name": str(name) if name is not None else None,
        "variant": raw.get("variant"),
        "quantity": quantity,
    }


def _as_counts(items: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in items:
        name = item.get("name")
        quantity = item.get("quantity")
        if not name or quantity is None:
            continue
        counts[name] = counts.get(name, 0) + int(quantity)
    return counts


def _granted_delta(
    previous: Optional[Dict[str, int]], current: Dict[str, int]
) -> Dict[str, int]:
    """Positive-only difference between two whole-inventory snapshots.

    ``set_inventory`` replaces the entire inventory, so the items *granted* by a
    given call are the entries whose count increased relative to the previous
    call. The first call in an episode is reported in full.
    """
    if previous is None:
        return dict(current)
    delta: Dict[str, int] = {}
    for name, quantity in current.items():
        gained = quantity - previous.get(name, 0)
        if gained > 0:
            delta[name] = gained
    return delta


def _caller_chain(max_frames: int = 12) -> List[Dict[str, Any]]:
    """Identify which repository function triggered the write.

    Frames belonging to this module are skipped so the first reported frame is
    the real caller (e.g. ``_fallback_mine_diamond_resource``).
    """
    chain: List[Dict[str, Any]] = []
    for frame_info in inspect.stack()[1:]:
        filename = frame_info.filename
        if filename == __file__:
            continue
        chain.append(
            {
                "file": Path(filename).name,
                "function": frame_info.function,
                "lineno": frame_info.lineno,
            }
        )
        if len(chain) >= max_frames:
            break
    return chain


class InventoryWriteLogger:
    """Wrap ``env.set_inventory`` and append one JSONL record per call."""

    def __init__(
        self,
        jsonl_path: str | Path,
        context: Optional[Mapping[str, Any]] = None,
        max_frames: int = 12,
    ):
        self.path = Path(jsonl_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.context: Dict[str, Any] = dict(context or {})
        self.max_frames = int(max_frames)
        self._lock = threading.Lock()
        self._env: Any = None
        self._original: Any = None
        self._call_index = 0
        self._previous_counts: Optional[Dict[str, int]] = None

    # -- lifecycle -----------------------------------------------------------

    def install(self, env: Any) -> Any:
        if self._env is not None:
            raise RuntimeError("InventoryWriteLogger is already installed")
        original = getattr(env, "set_inventory", None)
        if original is None:
            raise AttributeError("environment has no set_inventory to wrap")

        def wrapped(items, *args, **kwargs):
            self._record(items)
            return original(items, *args, **kwargs)

        wrapped.__wrapped__ = original  # type: ignore[attr-defined]
        env.set_inventory = wrapped  # type: ignore[assignment]
        self._env = env
        self._original = original
        return env

    def uninstall(self) -> None:
        if self._env is None:
            return
        try:
            self._env.set_inventory = self._original  # type: ignore[assignment]
        finally:
            self._env = None
            self._original = None

    def __enter__(self) -> "InventoryWriteLogger":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.uninstall()

    # -- recording -----------------------------------------------------------

    def _record(self, items: Any) -> None:
        normalised = [_item_to_mapping(item) for item in (items or [])]
        counts = _as_counts(normalised)
        granted = _granted_delta(self._previous_counts, counts)

        record: Dict[str, Any] = {
            "timestamp": _utc_now_iso(),
            "event_type": "inventory_write",
            "call_index": self._call_index,
            "granted": granted,
            "resulting_inventory": counts,
            "caller_chain": _caller_chain(self.max_frames),
        }
        record.update(self.context)

        line = json.dumps(record, sort_keys=True, ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            self._call_index += 1
            self._previous_counts = counts
