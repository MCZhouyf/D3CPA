"""Deterministic local-subgoal derivation for execution telemetry.

The legacy controller receives a workflow that does not naturally preserve the
semantic purpose of each :class:`PlanStep`.  Round 1.1 uses this helper in the
adapter, before the workflow enters the controller, so every step/action event
can carry a stable local subgoal without another LLM call.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


_METADATA_KEYS = (
    "local_subgoal",
    "subgoal",
    "description",
    "goal",
    "objective",
)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().replace("_", " ").split())


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _actions(step: Any) -> Sequence[Any]:
    value = getattr(step, "actions", None)
    if value is None and isinstance(step, Mapping):
        value = step.get("actions", ())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _action_name_and_args(action: Any) -> tuple[str, Mapping[str, Any]]:
    if isinstance(action, Mapping):
        return _clean(action.get("name") or action.get("type")).lower(), _as_mapping(
            action.get("args", action)
        )
    return _clean(getattr(action, "name", "")).lower(), _as_mapping(
        getattr(action, "args", {})
    )


def _primary_expected_output(step: Any) -> str:
    outputs = getattr(step, "expected_outputs", None)
    if outputs is None and isinstance(step, Mapping):
        outputs = step.get("expected_outputs", {})
    if not isinstance(outputs, Mapping) or not outputs:
        return ""
    # Deterministic: prefer the greatest requested quantity, then lexical order.
    ranked = sorted(
        ((float(quantity), _clean(item)) for item, quantity in outputs.items()),
        key=lambda pair: (-pair[0], pair[1]),
    )
    return ranked[0][1]


def _from_action(action: Any) -> str:
    name, args = _action_name_and_args(action)
    if not name:
        return ""

    if name == "craft":
        outputs = args.get("obj", {})
        if isinstance(outputs, Mapping) and outputs:
            return f"craft {_clean(next(iter(outputs)))}"
    if name == "mine":
        return f"mine {_clean(args.get('obj'))}".strip()
    if name in {"find", "move_to"}:
        # Local intent is the target object; preserve the action verb because
        # find and move_to can correspond to different scene requirements.
        return f"{name.replace('_', ' ')} {_clean(args.get('obj'))}".strip()
    if name == "equip":
        return f"equip {_clean(args.get('obj'))}".strip()
    if name == "fight":
        return f"fight {_clean(args.get('obj'))}".strip()
    if name == "apply":
        target = _clean(args.get("obj"))
        tool = _clean(args.get("tool"))
        return " ".join(part for part in ("apply", tool, "to", target) if part).strip()
    if name == "dig_down":
        level = _clean(args.get("y_level"))
        return f"dig down to y {level}".strip() if level else "dig down"
    if name == "dig_up":
        return "dig up"
    return name.replace("_", " ")


def resolve_local_subgoal(step: Any, *, fallback_index: int | None = None) -> str:
    """Return a stable, human-readable local subgoal for ``step``.

    Resolution order is intentionally conservative and deterministic:

    1. explicit semantic metadata;
    2. expected output of the plan step;
    3. first high-level action;
    4. stable step identifier;
    5. positional fallback.

    No LLM call or environment access occurs here.
    """

    metadata = getattr(step, "metadata", None)
    if metadata is None and isinstance(step, Mapping):
        metadata = step.get("metadata", {})
    metadata = _as_mapping(metadata)
    for key in _METADATA_KEYS:
        text = _clean(metadata.get(key))
        if text:
            return text

    expected = _primary_expected_output(step)
    if expected:
        return f"obtain {expected}"

    for action in _actions(step):
        text = _from_action(action)
        if text:
            return text

    step_id = _clean(getattr(step, "step_id", ""))
    if not step_id and isinstance(step, Mapping):
        step_id = _clean(step.get("step_id"))
    if step_id:
        return step_id

    if fallback_index is None:
        return "unspecified local subgoal"
    return f"step {int(fallback_index)}"
