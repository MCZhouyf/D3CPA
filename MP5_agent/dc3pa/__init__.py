"""DC3PA research implementation, stages 0-2.

Stages included:
- Stage 0: reproducible baseline launch, manifests, source audit, guarded legacy patches.
- Stage 1: typed contracts and adapters around the MP5 planner/controller boundary.
- Stage 2: persistent dependency-schema and scene-exemplar memory.
"""

from .config import DC3PAConfig, FeatureFlags, load_config
from .contracts import Action, AgentState, EpisodeTrace, Plan, PlanStep

__all__ = [
    "Action",
    "AgentState",
    "DC3PAConfig",
    "EpisodeTrace",
    "FeatureFlags",
    "Plan",
    "PlanStep",
    "load_config",
]

__version__ = "0.3.0"
