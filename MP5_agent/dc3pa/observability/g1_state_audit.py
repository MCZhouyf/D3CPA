"""External state-write observation for G1; never imported by Controller."""
from __future__ import annotations

import inspect
import itertools
from dataclasses import dataclass
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class StateWriteEvent:
    event_id: str
    source: str


class StateWriteObserver:
    """Wrap an environment's public setter outside protected callback code."""

    def __init__(self) -> None:
        self._counter = itertools.count(1)
        self.events: list[StateWriteEvent] = []

    def wrap_set_inventory(self, setter: Callable[[Iterable[Any]], Any]) -> Callable[[Iterable[Any]], Any]:
        def observed(items: Iterable[Any]) -> Any:
            source = "protected_log_callback" if any(
                frame.function == "_set_inventory_from_memory" and frame.filename.endswith("controller.py")
                for frame in inspect.stack(context=0)
            ) else "environment_reset"
            self.events.append(StateWriteEvent(f"state-{next(self._counter)}", source))
            return setter(items)
        return observed

    def attach(self, env: Any) -> None:
        env.set_inventory = self.wrap_set_inventory(env.set_inventory)
