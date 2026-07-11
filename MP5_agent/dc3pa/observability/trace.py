from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Mapping

from ..contracts import utc_now_iso


class JsonlTraceWriter:
    """Append-only structured trace writer safe for a single process with threads."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, event_type: str, payload: Mapping[str, Any]) -> None:
        record = {
            "timestamp": utc_now_iso(),
            "event_type": event_type,
            "payload": dict(payload),
        }
        serialized = json.dumps(record, sort_keys=True, ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(serialized + "\n")
