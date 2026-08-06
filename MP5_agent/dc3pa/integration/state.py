from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, runtime_checkable

import numpy as np

from ..contracts import AgentState
from ..memory.multimodal_memory import SceneObservation
from ..reliability import ReliabilityContext
from .events import InventorySnapshot, sanitize_for_trace


@dataclass(frozen=True)
class StateSnapshot:
    state: AgentState
    reliability_context: ReliabilityContext
    scene: Optional[SceneObservation] = None


@runtime_checkable
class StateProvider(Protocol):
    def snapshot(
        self, task_information: Mapping[str, Any], underground: bool
    ) -> StateSnapshot:
        ...


def task_name_from_information(task_information: Mapping[str, Any]) -> str:
    for key in ("task", "task_name", "description", "name"):
        value = task_information.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    raise ValueError("task_information must contain task/task_name/description/name")


def task_context_from_information(task_information: Mapping[str, Any]) -> str:
    task = task_name_from_information(task_information)
    quantity = task_information.get("quantity")
    if quantity is None:
        return task
    return f"{task}; requested quantity={quantity}"


def _extract_nested(mapping: Mapping[str, Any], key: str) -> Any:
    if key in mapping:
        return mapping[key]
    for nested_key in ("observation", "obs", "event", "events"):
        nested = mapping.get(nested_key)
        if isinstance(nested, Mapping) and key in nested:
            return nested[key]
    return None


def extract_rgb_observation(observation: Any) -> Optional[np.ndarray]:
    """Extract a defensive HWC RGB/RGBA copy from common MineDojo payload shapes."""

    candidate = observation
    if isinstance(observation, Mapping):
        candidate = None
        for key in ("rgb", "pov", "image"):
            found = _extract_nested(observation, key)
            if found is not None:
                candidate = found
                break
    if candidate is None or isinstance(candidate, (str, bytes)):
        return None
    try:
        array = np.asarray(candidate)
    except Exception:
        return None
    if array.ndim != 3:
        return None
    if array.shape[-1] not in (3, 4) and array.shape[0] in (3, 4):
        array = np.moveaxis(array, 0, -1)
    if array.shape[-1] not in (3, 4) or min(array.shape[:2]) <= 0:
        return None
    if not np.issubdtype(array.dtype, np.number):
        return None
    if not np.isfinite(array.astype(np.float64, copy=False)).all():
        return None
    if np.issubdtype(array.dtype, np.floating):
        maximum = float(array.max(initial=0.0))
        minimum = float(array.min(initial=0.0))
        if minimum >= 0.0 and maximum <= 1.0:
            array = np.rint(array * 255.0)
    array = np.clip(array, 0, 255).astype(np.uint8, copy=False)
    return np.ascontiguousarray(array.copy())


def extract_health(observation: Any) -> Optional[float]:
    if not isinstance(observation, Mapping):
        return None
    candidates = [
        observation.get("health"),
        observation.get("life"),
    ]
    life_stats = observation.get("life_stats")
    if isinstance(life_stats, Mapping):
        candidates.extend([life_stats.get("life"), life_stats.get("health")])
    for value in candidates:
        if value is None or isinstance(value, bool):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(number):
            return number
    return None


class LegacyMP5StateProvider:
    """Build Stage-6 state from callbacks without importing MineDojo.

    ``refresh_observation`` may perform the legacy no-op environment step and update
    ``Work_Memory``. The returned observation is used only for the current snapshot;
    raw image arrays are never placed in trace metadata.
    """

    def __init__(
        self,
        refresh_observation: Callable[[], Any],
        inventory_provider: Callable[[], Mapping[str, Any]],
        *,
        on_environment_reset: Optional[Callable[[], None]] = None,
        position_provider: Optional[Callable[[bool, Any], str]] = None,
        scene_description_factory: Optional[
            Callable[[str, Mapping[str, float], str, Any], str]
        ] = None,
    ):
        self.refresh_observation = refresh_observation
        self.inventory_provider = inventory_provider
        self._on_environment_reset = on_environment_reset
        self.position_provider = position_provider
        self.scene_description_factory = scene_description_factory

    def on_environment_reset(self) -> None:
        """Discard legacy state that cannot survive a fresh world reset."""
        if self._on_environment_reset is not None:
            self._on_environment_reset()

    def snapshot(
        self, task_information: Mapping[str, Any], underground: bool
    ) -> StateSnapshot:
        observation = self.refresh_observation()
        inventory = InventorySnapshot.from_mapping(self.inventory_provider()).to_dict()
        task = task_name_from_information(task_information)
        task_context = task_context_from_information(task_information)
        position = (
            self.position_provider(underground, observation)
            if self.position_provider is not None
            else ("underground" if underground else "surface_or_unknown")
        )
        image = extract_rgb_observation(observation)
        state = AgentState(
            task=task,
            inventory=inventory,
            position=str(position),
            health=extract_health(observation),
            metadata={
                "underground": bool(underground),
                "observation_type": type(observation).__name__,
            },
        )
        context = ReliabilityContext(
            task_context=task_context,
            image=image,
            metadata={
                "underground": bool(underground),
                "task_information": sanitize_for_trace(dict(task_information)),
            },
        )
        if self.scene_description_factory is not None:
            description = self.scene_description_factory(
                task, inventory, str(position), observation
            )
        else:
            item_summary = ", ".join(
                f"{name}={quantity:g}" for name, quantity in sorted(inventory.items())
            ) or "empty inventory"
            description = f"task={task}; position={position}; inventory={item_summary}"
        scene = SceneObservation(
            description=str(description),
            task_context=task_context,
            inventory=inventory,
            position=str(position),
            image=image,
            metadata={"underground": bool(underground)},
        )
        return StateSnapshot(state=state, reliability_context=context, scene=scene)
