from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Sequence

from ..contracts import AgentState, Plan
from ..memory.encoders import as_float_vector
from ..memory.exemplar_store import SceneExemplar, normalized_cosine
from ..memory.multimodal_memory import MultimodalMemory
from .contracts import DimensionScore, ReliabilityContext


ENVIRONMENT_IMPLS = frozenset({"legacy_v1", "shadow_v2", "topk_v2"})
ENVIRONMENT_SCOPES = frozenset({"legacy_all_steps", "current_context_only"})

ENVIRONMENT_STATUSES = frozenset(
    {
        "matched",
        "mismatch",
        "unknown",
        "technical_unavailable",
        "future_context_unavailable",
    }
)

_ENVIRONMENT_ACTION_PRIORITY = (
    "find",
    "move_to",
    "mine",
    "fight",
    "dig_down",
    "dig_up",
    "apply",
    "equip",
    "craft",
)


def validate_environment_impl(value: str) -> str:
    candidate = str(value or "").strip().lower()
    if candidate not in ENVIRONMENT_IMPLS:
        raise ValueError(
            f"environment_impl must be one of {sorted(ENVIRONMENT_IMPLS)}, got {value!r}"
        )
    return candidate


def validate_environment_scope(value: str) -> str:
    candidate = str(value or "").strip().lower()
    if candidate not in ENVIRONMENT_SCOPES:
        raise ValueError(
            f"environment_scope must be one of {sorted(ENVIRONMENT_SCOPES)}, got {value!r}"
        )
    return candidate


def _clean_token(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9 .:/+-]", "", text)
    return text.strip()


def _slug(value: Any) -> str:
    return _clean_token(value).replace(" ", "_")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _metadata(step: Any) -> Mapping[str, Any]:
    value = getattr(step, "metadata", None)
    if value is None and isinstance(step, Mapping):
        value = step.get("metadata", {})
    return _mapping(value)


def _expected_outputs(step: Any) -> Mapping[str, Any]:
    value = getattr(step, "expected_outputs", None)
    if value is None and isinstance(step, Mapping):
        value = step.get("expected_outputs", {})
    return _mapping(value)


def _action_name_args(action: Any) -> tuple[str, Mapping[str, Any]]:
    if isinstance(action, Mapping):
        return (
            _clean_token(action.get("name") or action.get("type")).replace(" ", "_"),
            _mapping(action.get("args", action)),
        )
    return (
        _clean_token(getattr(action, "name", "")).replace(" ", "_"),
        _mapping(getattr(action, "args", {})),
    )


def _primary_obj(value: Any) -> str:
    if isinstance(value, Mapping):
        if not value:
            return ""
        # Stable order. Quantity does not belong in the action key.
        return _slug(sorted(str(key) for key in value)[0])
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return _slug(value[0]) if value else ""
    return _slug(value)


def _resolve_local_subgoal(step: Any, *, fallback_index: int) -> str:
    for key in ("local_subgoal", "subgoal", "description", "goal", "objective"):
        text = _clean_token(_metadata(step).get(key))
        if text:
            return text
    expected = _expected_outputs(step)
    if expected:
        ranked = sorted(
            ((float(quantity), _clean_token(item)) for item, quantity in expected.items()),
            key=lambda pair: (-pair[0], pair[1]),
        )
        if ranked[0][1]:
            return f"obtain {ranked[0][1]}"
    action_key = canonical_action_key(select_environment_action(step))
    if action_key:
        return action_key.replace(":", " ").replace("_", " ")
    step_id = _clean_token(getattr(step, "step_id", ""))
    if not step_id and isinstance(step, Mapping):
        step_id = _clean_token(step.get("step_id"))
    return step_id or f"step {int(fallback_index)}"


def canonical_action_key(action: Any) -> str:
    """Return a stable, non-LLM action key used by local exemplar retrieval.

    The key intentionally captures the high-level operation and its primary
    target, not the entire action payload. Examples:
      ``mine:cobblestone``, ``find:tree``, ``craft:wooden_pickaxe``.
    """

    name, args = _action_name_args(action)
    if not name:
        return ""

    if name in {"find", "move_to", "mine", "fight", "equip", "craft"}:
        target = _primary_obj(args.get("obj"))
        return f"{name}:{target}" if target else name

    if name == "apply":
        tool = _primary_obj(args.get("tool"))
        target = _primary_obj(args.get("obj"))
        suffix = ":".join(part for part in (tool, target) if part)
        return f"apply:{suffix}" if suffix else "apply"

    if name == "dig_down":
        level = _slug(args.get("y_level"))
        return f"dig_down:{level}" if level else "dig_down"

    if name == "dig_up":
        return "dig_up"

    target = _primary_obj(args.get("obj"))
    return f"{name}:{target}" if target else name


def select_environment_action(step: Any) -> Any:
    actions = getattr(step, "actions", ())
    if not actions and isinstance(step, Mapping):
        actions = step.get("actions", ())
    actions = tuple(actions or ())
    if not actions:
        return None

    by_name: dict[str, list[Any]] = {}
    for action in actions:
        name, _ = _action_name_args(action)
        by_name.setdefault(name, []).append(action)
    for name in _ENVIRONMENT_ACTION_PRIORITY:
        if by_name.get(name):
            return by_name[name][0]
    return actions[0]


def _action_from_context_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        if "name" in value or "type" in value:
            return value
        for key in ("action", "next_action", "high_level_action"):
            if key in value:
                return _action_from_context_value(value[key])
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = json.loads(stripped)
        except Exception:
            return None
        return _action_from_context_value(parsed)
    return None


def _fallback_key_from_text(text: str) -> str:
    normalized = _clean_token(text)
    patterns = (
        ("move to ", "move_to"),
        ("dig down", "dig_down"),
        ("dig up", "dig_up"),
        ("find ", "find"),
        ("mine ", "mine"),
        ("craft ", "craft"),
        ("fight ", "fight"),
        ("equip ", "equip"),
    )
    for prefix, name in patterns:
        if normalized.startswith(prefix):
            target = normalized[len(prefix) :].strip()
            return f"{name}:{_slug(target)}" if target else name
    return ""


def exemplar_action_key(exemplar: SceneExemplar) -> tuple[str, str]:
    """Return ``(key, source)`` for a stored exemplar.

    Structured metadata is authoritative. Text fallback is deliberately
    conservative and is only intended for legacy snapshots.
    """

    metadata = dict(exemplar.metadata or {})
    explicit = _clean_token(metadata.get("action_key")).replace(" ", "_")
    if explicit:
        return explicit, "metadata.action_key"

    for value, source in (
        (metadata.get("action"), "metadata.action"),
        (metadata.get("next_action"), "metadata.next_action"),
        (exemplar.task_context, "task_context"),
    ):
        action = _action_from_context_value(value)
        if action is not None:
            key = canonical_action_key(action)
            if key:
                return key, source

    for value, source in (
        (exemplar.description, "description_fallback"),
        (exemplar.task_context, "task_context_fallback"),
    ):
        key = _fallback_key_from_text(str(value or ""))
        if key:
            return key, source
    return "", "unavailable"


@dataclass(frozen=True)
class EnvironmentMatchV2:
    exemplar_id: str
    episode_id: str
    action_key: str
    action_key_source: str
    local_subgoal: str
    visual_similarity: float
    semantic_relevance: float
    joint_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EnvironmentEvidenceV2:
    available: bool
    status: str
    compatibility: Optional[float]
    coverage: float
    query_action_key: str
    query_local_subgoal: str
    candidate_count: int
    relevant_candidate_count: int
    matches: tuple[EnvironmentMatchV2, ...] = ()
    scope_reason: str = ""
    neutral_compatibility_for_future_fusion: float = 0.5

    def __post_init__(self) -> None:
        if self.status not in ENVIRONMENT_STATUSES:
            raise ValueError(f"Unknown environment status {self.status!r}")
        if not 0.0 <= float(self.coverage) <= 1.0:
            raise ValueError("coverage must be in [0, 1]")
        if self.available != (self.compatibility is not None):
            raise ValueError("available must match whether compatibility is present")
        if self.compatibility is not None and not 0.0 <= float(self.compatibility) <= 1.0:
            raise ValueError("compatibility must be in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["matches"] = [match.to_dict() for match in self.matches]
        return payload


class EnvironmentReliabilityStrategyV2:
    """Action-conditioned top-k environment evidence.

    No LLM or environment call is made here. Existing image/text encoders and
    frozen Scene Exemplars are reused. Unknown memory coverage is represented as
    an unavailable environment dimension plus explicit neutral/coverage fields;
    it is not converted into a false zero-probability failure.
    """

    def __init__(
        self,
        memory: MultimodalMemory,
        *,
        top_k: int = 3,
        text_threshold: float = 0.5,
        match_threshold: float = 0.5,
        scope: str = "current_context_only",
        require_text_relevance: bool = True,
        task_name_filter: bool = False,
        allow_legacy_text_fallback: bool = True,
    ):
        if isinstance(top_k, bool) or int(top_k) <= 0:
            raise ValueError("top_k must be a positive integer")
        for value, label in (
            (text_threshold, "text_threshold"),
            (match_threshold, "match_threshold"),
        ):
            if isinstance(value, bool) or not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{label} must be in [0, 1]")
        self.memory = memory
        self.top_k = int(top_k)
        self.text_threshold = float(text_threshold)
        self.match_threshold = float(match_threshold)
        self.scope = validate_environment_scope(scope)
        self.require_text_relevance = bool(require_text_relevance)
        self.task_name_filter = bool(task_name_filter)
        self.allow_legacy_text_fallback = bool(allow_legacy_text_fallback)

    def _current_image_vector(self, context: ReliabilityContext):
        if context.image_vector is not None:
            return as_float_vector(context.image_vector)
        if context.image is not None and self.memory.image_encoder is not None:
            return as_float_vector(self.memory.image_encoder.encode_image(context.image))
        return None

    def _query_text_vector(
        self, local_subgoal: str, action_key: str, context: ReliabilityContext
    ):
        explicit = context.metadata.get("environment_query_text_vector")
        if explicit is not None:
            return as_float_vector(explicit)
        if self.memory.text_encoder is None:
            return None
        return as_float_vector(
            self.memory.text_encoder.encode_text(f"{local_subgoal}\n{action_key}")
        )

    def _text_vector_for(self, exemplar: SceneExemplar, action_key: str):
        if exemplar.text_vector is not None:
            return as_float_vector(exemplar.text_vector)
        if self.memory.text_encoder is None:
            return None
        return as_float_vector(
            self.memory.text_encoder.encode_text(
                f"{exemplar.description}\n{action_key}\n{exemplar.task_context}"
            )
        )

    def _scope_evidence(
        self,
        *,
        plan: Plan,
        step_index: int,
        context: ReliabilityContext,
        local_subgoal: str,
        action_key: str,
    ) -> Optional[EnvironmentEvidenceV2]:
        if self.scope == "legacy_all_steps":
            return None
        if "environment_step_index" not in context.metadata:
            return EnvironmentEvidenceV2(
                available=False,
                status="future_context_unavailable",
                compatibility=None,
                coverage=0.0,
                query_action_key=action_key,
                query_local_subgoal=local_subgoal,
                candidate_count=0,
                relevant_candidate_count=0,
                scope_reason=(
                    "Current observation step is not specified; refusing to "
                    "reuse it as plan-step evidence"
                ),
            )
        target_index = context.metadata.get("environment_step_index")
        try:
            target_index = int(target_index)
        except (TypeError, ValueError):
            return EnvironmentEvidenceV2(
                available=False,
                status="future_context_unavailable",
                compatibility=None,
                coverage=0.0,
                query_action_key=action_key,
                query_local_subgoal=local_subgoal,
                candidate_count=0,
                relevant_candidate_count=0,
                scope_reason=(
                    "Current observation step is invalid; refusing to use it "
                    "as plan-step evidence"
                ),
            )
        if step_index == target_index:
            return None
        return EnvironmentEvidenceV2(
            available=False,
            status="future_context_unavailable",
            compatibility=None,
            coverage=0.0,
            query_action_key=action_key,
            query_local_subgoal=local_subgoal,
            candidate_count=0,
            relevant_candidate_count=0,
            scope_reason=(
                f"Current observation is assigned to plan step {target_index}, "
                f"not future step {step_index}"
            ),
        )

    def evaluate(
        self,
        plan: Plan,
        step_index: int,
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
    ) -> EnvironmentEvidenceV2:
        del state
        context = context or ReliabilityContext()
        step = plan.steps[step_index]
        local_subgoal = _resolve_local_subgoal(step, fallback_index=step_index)
        action = select_environment_action(step)
        action_key = canonical_action_key(action)

        scope_evidence = self._scope_evidence(
            plan=plan,
            step_index=step_index,
            context=context,
            local_subgoal=local_subgoal,
            action_key=action_key,
        )
        if scope_evidence is not None:
            return scope_evidence

        try:
            current_image = self._current_image_vector(context)
        except Exception as exc:
            return EnvironmentEvidenceV2(
                available=False,
                status="technical_unavailable",
                compatibility=None,
                coverage=0.0,
                query_action_key=action_key,
                query_local_subgoal=local_subgoal,
                candidate_count=0,
                relevant_candidate_count=0,
                scope_reason=f"Current image encoding failed: {type(exc).__name__}: {exc}",
            )
        if current_image is None:
            return EnvironmentEvidenceV2(
                available=False,
                status="technical_unavailable",
                compatibility=None,
                coverage=0.0,
                query_action_key=action_key,
                query_local_subgoal=local_subgoal,
                candidate_count=0,
                relevant_candidate_count=0,
                scope_reason="No current visual observation or image vector is available",
            )

        try:
            query_text = self._query_text_vector(local_subgoal, action_key, context)
            exemplars = self.memory.exemplars.all(
                task_name=plan.task if self.task_name_filter else None
            )
        except Exception as exc:
            return EnvironmentEvidenceV2(
                available=False,
                status="technical_unavailable",
                compatibility=None,
                coverage=0.0,
                query_action_key=action_key,
                query_local_subgoal=local_subgoal,
                candidate_count=0,
                relevant_candidate_count=0,
                scope_reason=f"Exemplar loading failed: {type(exc).__name__}: {exc}",
            )

        action_candidates: list[tuple[SceneExemplar, str, str]] = []
        for exemplar in exemplars:
            candidate_key, key_source = exemplar_action_key(exemplar)
            if action_key and candidate_key == action_key:
                action_candidates.append((exemplar, candidate_key, key_source))
            elif (
                self.allow_legacy_text_fallback
                and not candidate_key
                and key_source == "unavailable"
            ):
                action_candidates.append((exemplar, candidate_key, key_source))

        if not action_candidates:
            return EnvironmentEvidenceV2(
                available=False,
                status="unknown",
                compatibility=None,
                coverage=0.0,
                query_action_key=action_key,
                query_local_subgoal=local_subgoal,
                candidate_count=len(exemplars),
                relevant_candidate_count=0,
                scope_reason="No action-conditioned Scene Exemplar is available",
            )

        scored: list[EnvironmentMatchV2] = []
        semantic_values: list[float] = []
        technical_text_failures = 0
        for exemplar, candidate_key, key_source in action_candidates:
            try:
                candidate_text = self._text_vector_for(
                    exemplar, candidate_key or action_key
                )
                relevance = normalized_cosine(query_text, candidate_text)
            except Exception:
                technical_text_failures += 1
                continue

            if relevance is None:
                if self.require_text_relevance:
                    technical_text_failures += 1
                    continue
                relevance_value = 1.0 if candidate_key == action_key and action_key else 0.0
            else:
                relevance_value = float(relevance)
            semantic_values.append(relevance_value)
            if relevance_value < self.text_threshold:
                continue

            visual = normalized_cosine(current_image, exemplar.image_vector)
            if visual is None:
                continue
            joint = float(visual) * relevance_value
            scored.append(
                EnvironmentMatchV2(
                    exemplar_id=exemplar.exemplar_id,
                    episode_id=exemplar.episode_id,
                    action_key=candidate_key or action_key,
                    action_key_source=key_source,
                    local_subgoal=exemplar.description,
                    visual_similarity=float(visual),
                    semantic_relevance=relevance_value,
                    joint_score=joint,
                )
            )

        coverage = max(semantic_values, default=0.0)
        if not scored:
            reason = (
                "No candidate met the semantic relevance threshold"
                if semantic_values
                else "No candidate supplied compatible text and visual evidence"
            )
            status = "unknown" if semantic_values else "technical_unavailable"
            return EnvironmentEvidenceV2(
                available=False,
                status=status,
                compatibility=None,
                coverage=coverage,
                query_action_key=action_key,
                query_local_subgoal=local_subgoal,
                candidate_count=len(action_candidates),
                relevant_candidate_count=0,
                scope_reason=(
                    f"{reason}; text_failures={technical_text_failures}"
                ),
            )

        scored.sort(key=lambda item: (-item.joint_score, item.exemplar_id))
        top_matches = tuple(scored[: self.top_k])
        compatibility = sum(item.joint_score for item in top_matches) / len(top_matches)
        compatibility = max(0.0, min(1.0, float(compatibility)))
        status = "matched" if compatibility >= self.match_threshold else "mismatch"
        return EnvironmentEvidenceV2(
            available=True,
            status=status,
            compatibility=compatibility,
            coverage=coverage,
            query_action_key=action_key,
            query_local_subgoal=local_subgoal,
            candidate_count=len(action_candidates),
            relevant_candidate_count=len(scored),
            matches=top_matches,
            scope_reason="Action-conditioned top-k environment evidence",
        )

    def score(
        self,
        plan: Plan,
        step_index: int,
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
    ) -> DimensionScore:
        evidence = self.evaluate(plan, step_index, state, context)
        if not evidence.available:
            return DimensionScore.unavailable(
                "environment",
                evidence.scope_reason or f"Environment evidence status: {evidence.status}",
                evidence=evidence.to_dict(),
            )
        return DimensionScore(
            dimension="environment",
            probability=evidence.compatibility,
            available=True,
            reason=(
                "Computed from action-conditioned top-k Scene Exemplars "
                f"({evidence.status})"
            ),
            evidence=evidence.to_dict(),
        )


class EnvironmentShadowStrategy:
    """Keep legacy environment decisions while recording candidate V2 evidence."""

    def __init__(self, legacy_strategy: Any, candidate_strategy: EnvironmentReliabilityStrategyV2):
        self.legacy_strategy = legacy_strategy
        self.candidate_strategy = candidate_strategy

    def score(
        self,
        plan: Plan,
        step_index: int,
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
    ) -> DimensionScore:
        legacy = self.legacy_strategy.score(plan, step_index, state, context)
        try:
            shadow = self.candidate_strategy.evaluate(plan, step_index, state, context)
            shadow_payload: Mapping[str, Any] = shadow.to_dict()
        except Exception as exc:  # Shadow must never change legacy behaviour.
            shadow_payload = {
                "available": False,
                "status": "technical_unavailable",
                "error": f"{type(exc).__name__}: {exc}",
            }
        evidence = dict(legacy.evidence)
        evidence["shadow_v2"] = dict(shadow_payload)
        return DimensionScore(
            dimension=legacy.dimension,
            probability=legacy.probability,
            available=legacy.available,
            reason=legacy.reason,
            evidence=evidence,
            hard_conflict=legacy.hard_conflict,
        )
