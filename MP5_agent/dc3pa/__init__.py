"""DC3PA research implementation, stages 0-5.

Stages included:
- Stage 0: reproducible baseline launch, manifests, source audit, guarded legacy patches.
- Stage 1: typed contracts and adapters around the MP5 planner/controller boundary.
- Stage 2: persistent dependency-schema and scene-exemplar memory.
- Stage 3: knowledge/model/environment reliability and weighted probability fusion.
- Stage 4: structured dual-chain evaluation and atomic plan revision at fixed M=1.
- Stage 5: uncertainty-driven adaptive evaluation cadence.

Minecraft runner integration remains a Stage-6 concern; importing this package does not
start MineDojo or call a real LLM.
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

__version__ = "0.6.0"
