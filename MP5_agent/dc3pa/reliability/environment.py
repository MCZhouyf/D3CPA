from __future__ import annotations

from typing import Any, Dict, Optional

from ..contracts import AgentState, Plan
from ..memory.encoders import as_float_vector
from ..memory.exemplar_store import SceneExemplar, normalized_cosine
from ..memory.multimodal_memory import MultimodalMemory
from .contracts import DimensionScore, ReliabilityContext


class EnvironmentReliabilityStrategy:
    """Paper-form environment score: best visual match, then task relevance."""

    def __init__(
        self,
        memory: MultimodalMemory,
        visual_similarity_weight: float = 0.7,
        require_text_relevance: bool = True,
        task_name_filter: bool = False,
    ):
        if not 0.0 <= visual_similarity_weight <= 1.0:
            raise ValueError("visual_similarity_weight must be in [0, 1]")
        self.memory = memory
        self.visual_similarity_weight = float(visual_similarity_weight)
        self.require_text_relevance = require_text_relevance
        self.task_name_filter = task_name_filter

    def _current_image_vector(self, context: ReliabilityContext):
        if context.image_vector is not None:
            return as_float_vector(context.image_vector)
        if context.image is not None and self.memory.image_encoder is not None:
            return as_float_vector(self.memory.image_encoder.encode_image(context.image))
        return None

    def _query_text_vector(self, plan: Plan, step_index: int, context: ReliabilityContext):
        if self.memory.text_encoder is None:
            return None
        text = context.task_context.strip()
        if not text:
            text = f"{plan.task}\n{plan.steps[step_index].to_dict()}"
        return as_float_vector(self.memory.text_encoder.encode_text(text))

    def _text_vector_for(self, exemplar: SceneExemplar):
        if exemplar.text_vector is not None:
            return as_float_vector(exemplar.text_vector)
        if self.memory.text_encoder is None:
            return None
        return as_float_vector(
            self.memory.text_encoder.encode_text(
                f"{exemplar.description}\n{exemplar.task_context}"
            )
        )

    def score(
        self,
        plan: Plan,
        step_index: int,
        state: AgentState,
        context: Optional[ReliabilityContext] = None,
    ) -> DimensionScore:
        del state  # Environment evidence is supplied through ReliabilityContext.
        context = context or ReliabilityContext()
        try:
            current_image = self._current_image_vector(context)
        except Exception as exc:
            return DimensionScore.unavailable(
                "environment",
                f"Current image encoding failed: {type(exc).__name__}",
                evidence={"error": str(exc)},
            )
        if current_image is None:
            return DimensionScore.unavailable(
                "environment",
                "No current visual observation or image vector is available",
            )
        try:
            exemplars = self.memory.exemplars.all(
                task_name=plan.task if self.task_name_filter else None
            )
            visual_candidates = []
            for exemplar in exemplars:
                similarity = normalized_cosine(current_image, exemplar.image_vector)
                if similarity is not None:
                    visual_candidates.append(
                        (float(similarity), exemplar.exemplar_id, exemplar)
                    )
            if not visual_candidates:
                return DimensionScore.unavailable(
                    "environment",
                    "No dimension-compatible visual exemplar is available",
                    evidence={"candidate_count": len(exemplars)},
                )
            visual_candidates.sort(key=lambda item: (-item[0], item[1]))
            s_max, _, best = visual_candidates[0]
            query_text = self._query_text_vector(plan, step_index, context)
            relevance = normalized_cosine(query_text, self._text_vector_for(best))
        except Exception as exc:
            return DimensionScore.unavailable(
                "environment",
                f"Exemplar retrieval or relevance encoding failed: {type(exc).__name__}",
                evidence={"error": str(exc)},
            )
        if relevance is None and self.require_text_relevance:
            return DimensionScore.unavailable(
                "environment",
                "Best visual exemplar lacks a compatible task-relevance signal",
                evidence={
                    "exemplar_id": best.exemplar_id,
                    "visual_similarity": s_max,
                },
            )
        relevance_value = float(relevance) if relevance is not None else 0.0
        alpha = self.visual_similarity_weight
        probability = s_max * (alpha + (1.0 - alpha) * relevance_value)
        probability = max(0.0, min(1.0, float(probability)))
        evidence: Dict[str, Any] = {
            "exemplar_id": best.exemplar_id,
            "episode_id": best.episode_id,
            "exemplar_task": best.task_name,
            "visual_similarity": s_max,
            "task_relevance": relevance,
            "visual_similarity_weight": alpha,
            "formula": "Smax * (alpha + (1-alpha) * R)",
            "visual_candidate_count": len(visual_candidates),
        }
        return DimensionScore(
            dimension="environment",
            probability=probability,
            available=True,
            reason="Computed from the best visual exemplar and its task relevance",
            evidence=evidence,
        )
