"""Five-level verbal confidence strategy for DC3PA Round 3.

One provider call yields one ordinal level.  Base and calibrated probabilities are both
looked up locally, so shadow/calibrated modes do not add LLM calls.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Mapping, Optional

from ..contracts import AgentState, Plan
from .confidence_observation import ConfidenceObservationCollector, ModelConfidenceObservation
from .contracts import ConfidenceRequest, DimensionScore, ReliabilityContext
from .model import ConfidenceProvider
from .ordinal_calibration import OrdinalCalibrationArtifact
from .ordinal_levels import BASE_ORDINAL_MAPPING, normalize_ordinal_level, validate_model_confidence_impl
from .projection import project_inventory

_CODE_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.IGNORECASE | re.DOTALL)
_ORDINAL_INSTRUCTION = (
    "Assess only the proposed step's chance of succeeding in the given state. "
    "Return one JSON object with exactly the keys confidence_level and reason. "
    "confidence_level must be exactly one of: very_unlikely, unlikely, uncertain, "
    "likely, very_likely. Keep reason concise and do not provide hidden chain-of-thought."
)


def ordinal_prompt_template_sha256() -> str:
    return hashlib.sha256(_ORDINAL_INSTRUCTION.encode("utf-8")).hexdigest()


def build_ordinal_confidence_prompt(request: ConfidenceRequest) -> str:
    return _ORDINAL_INSTRUCTION + "\n" + json.dumps(
        request.to_prompt_payload(), sort_keys=True, ensure_ascii=False, default=str
    )


def _strip_fence(text: str) -> str:
    match = _CODE_FENCE.match(text.strip())
    return match.group(1) if match else text.strip()


def parse_ordinal_confidence(raw: Any) -> tuple[str, str, Dict[str, Any]]:
    metadata: Dict[str, Any] = {}
    value = raw
    if isinstance(raw, str):
        stripped = _strip_fence(raw)
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError("ordinal confidence must be a JSON object") from exc
        metadata["input_format"] = "json_string"
    if not isinstance(value, Mapping):
        raise ValueError("ordinal confidence must be a mapping")
    if "confidence_level" not in value:
        raise ValueError("ordinal confidence mapping lacks confidence_level")
    level = normalize_ordinal_level(value["confidence_level"])
    reason = str(value.get("reason", "")).strip()
    metadata["protocol"] = "ordinal_v2"
    return level, reason, metadata


class OrdinalConfidenceStrategy:
    def __init__(
        self,
        provider: ConfidenceProvider,
        *,
        implementation: str = "ordinal_v2",
        model_id: str,
        prompt_version: str = "ordinal-v1",
        artifact: Optional[OrdinalCalibrationArtifact] = None,
        observer: Optional[ConfidenceObservationCollector] = None,
        failure_mode: str = "unavailable",
        cache_enabled: bool = True,
    ) -> None:
        implementation = validate_model_confidence_impl(implementation)
        if implementation == "legacy_numeric":
            raise ValueError("legacy_numeric must use the existing VerbalConfidenceStrategy")
        if failure_mode not in {"unavailable", "raise"}:
            raise ValueError("failure_mode must be 'unavailable' or 'raise'")
        if not str(model_id).strip() or not str(prompt_version).strip():
            raise ValueError("model_id and prompt_version are required")
        prompt_hash = ordinal_prompt_template_sha256()
        if implementation in {"ordinal_shadow", "ordinal_calibrated"}:
            if artifact is None:
                raise ValueError(f"{implementation} requires a calibration artifact")
            artifact.validate_compatibility(
                model_id=str(model_id),
                prompt_version=str(prompt_version),
                prompt_sha256=prompt_hash,
            )
        self.provider = provider
        self.implementation = implementation
        self.model_id = str(model_id)
        self.prompt_version = str(prompt_version)
        self.prompt_sha256 = prompt_hash
        self.artifact = artifact
        self.observer = observer
        self.failure_mode = failure_mode
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, tuple[DimensionScore, ModelConfidenceObservation]] = {}

    def _request_hash(self, request: ConfidenceRequest) -> str:
        payload = {
            "request": request.to_prompt_payload(),
            "implementation": self.implementation,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
            "prompt_sha256": self.prompt_sha256,
        }
        encoded = json.dumps(
            payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _record(self, observation: ModelConfidenceObservation) -> None:
        if self.observer is not None:
            self.observer.record(observation)

    def score(
        self,
        plan: Plan,
        step_index: int,
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
    ) -> DimensionScore:
        projected_state = state
        try:
            projected_inventory = project_inventory(plan, state).before(step_index)
            projected_state = AgentState(
                task=state.task,
                inventory=projected_inventory,
                position=state.position,
                health=state.health,
                observation_ref=state.observation_ref,
                voxel_summary=state.voxel_summary,
                metadata={
                    **dict(state.metadata),
                    "dc3pa_original_inventory": dict(state.inventory),
                    "dc3pa_projected_inventory": projected_inventory,
                    "dc3pa_projection_step_index": step_index,
                },
            )
        except Exception:
            projected_inventory = None
        request = ConfidenceRequest(
            plan=plan,
            state=projected_state,
            step_index=step_index,
            context=context or ReliabilityContext(),
        )
        request_hash = self._request_hash(request)
        if self.cache_enabled and request_hash in self._cache:
            cached_score, cached_observation = self._cache[request_hash]
            evidence = dict(cached_score.evidence)
            evidence["cache_hit"] = True
            score = DimensionScore(
                dimension="model",
                probability=cached_score.probability,
                available=True,
                reason=cached_score.reason,
                evidence=evidence,
            )
            self._record(
                ModelConfidenceObservation(
                    **{
                        **cached_observation.to_dict(),
                        "cache_hit": True,
                        "episode_id": "",
                    }
                )
            )
            return score
        try:
            raw = self.provider.confidence(request)
            level, reason, parser_metadata = parse_ordinal_confidence(raw)
            base_probability = float(BASE_ORDINAL_MAPPING[level])
            calibrated_probability = (
                self.artifact.probability(level) if self.artifact is not None else None
            )
            if self.implementation == "ordinal_calibrated":
                assert calibrated_probability is not None
                decision_probability = calibrated_probability
                probability_source = "calibrated"
            else:
                decision_probability = base_probability
                probability_source = "base"
            artifact_id = self.artifact.artifact_id if self.artifact is not None else ""
            evidence = {
                "confidence_protocol": "ordinal_v2",
                "confidence_level": level,
                "base_probability": base_probability,
                "calibrated_probability": calibrated_probability,
                "decision_probability_source": probability_source,
                "model_id": self.model_id,
                "prompt_version": self.prompt_version,
                "prompt_sha256": self.prompt_sha256,
                "calibration_artifact_id": artifact_id,
                "request_hash": request_hash,
                "cache_hit": False,
                "metadata": {
                    **parser_metadata,
                    "projected_inventory_used": projected_inventory is not None,
                },
            }
            score = DimensionScore(
                dimension="model",
                probability=decision_probability,
                available=True,
                reason=reason or "Provider returned ordinal confidence",
                evidence=evidence,
            )
            step = plan.steps[step_index]
            observation = ModelConfidenceObservation(
                plan_id=plan.plan_id,
                plan_version=plan.version,
                step_id=step.step_id,
                step_index=step_index,
                request_hash=request_hash,
                implementation=self.implementation,
                confidence_level=level,
                base_probability=base_probability,
                calibrated_probability=calibrated_probability,
                decision_probability=decision_probability,
                model_id=self.model_id,
                prompt_version=self.prompt_version,
                prompt_sha256=self.prompt_sha256,
                calibration_artifact_id=artifact_id,
                cache_hit=False,
                metadata={"probability_source": probability_source},
            )
            self._record(observation)
            if self.cache_enabled:
                self._cache[request_hash] = (score, observation)
            return score
        except Exception as exc:
            if self.failure_mode == "raise":
                raise
            return DimensionScore.unavailable(
                "model",
                f"Ordinal confidence provider failed: {type(exc).__name__}",
                evidence={
                    "error": str(exc),
                    "confidence_protocol": "ordinal_v2",
                    "model_id": self.model_id,
                    "prompt_version": self.prompt_version,
                    "request_hash": request_hash,
                    "cache_hit": False,
                },
            )
