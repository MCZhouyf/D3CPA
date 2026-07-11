from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Optional

_TASK_LINE = re.compile(
    r"Task (?P<task>.*?) \| Iteration (?P<iteration>\d+) \| Successful "
    r"(?P<success>True|False) \| Episode length (?P<rounds>\d+) \| "
    r"Success rate (?P<rate>[0-9.]+)"
)


@dataclass(frozen=True)
class LegacyEpisodeMetrics:
    task: str
    iteration: int
    success: bool
    planning_rounds: int
    replanning_count: int
    invalid_plan_retries: int
    cumulative_success_rate: float


@dataclass(frozen=True)
class LegacyRunMetrics:
    episodes: List[LegacyEpisodeMetrics]
    wall_clock_seconds: float
    return_code: int

    @property
    def success_rate(self) -> Optional[float]:
        if not self.episodes:
            return None
        return sum(episode.success for episode in self.episodes) / len(self.episodes)

    @property
    def average_replanning_count(self) -> Optional[float]:
        if not self.episodes:
            return None
        return sum(episode.replanning_count for episode in self.episodes) / len(self.episodes)

    def to_dict(self):
        return {
            "episodes": [asdict(episode) for episode in self.episodes],
            "wall_clock_seconds": self.wall_clock_seconds,
            "return_code": self.return_code,
            "success_rate": self.success_rate,
            "average_replanning_count": self.average_replanning_count,
            "notes": {
                "planning_rounds": (
                    "Derived from the legacy 'Episode length' field, which increments once "
                    "per planning/execution round in run_agent.py."
                ),
                "replanning_count": (
                    "max(planning_rounds - 1, 0); this approximates reactive replanning "
                    "after a valid workflow reached execution"
                ),
                "invalid_plan_retries": (
                    "Counted separately from log lines emitted when the planner returned "
                    "an empty or invalid workflow before Controller execution"
                ),
                "wall_clock_seconds": (
                    "Measured around the complete legacy process; it is not a pure LLM-only latency."
                ),
            },
        }

    def write(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def parse_legacy_metrics(
    lines: Iterable[str], wall_clock_seconds: float, return_code: int
) -> LegacyRunMetrics:
    episodes: List[LegacyEpisodeMetrics] = []
    pending_invalid_plan_retries = 0
    for line in lines:
        if "Planner did not return a valid workflow" in line:
            pending_invalid_plan_retries += 1
        match = _TASK_LINE.search(line)
        if not match:
            continue
        rounds = int(match.group("rounds"))
        episodes.append(
            LegacyEpisodeMetrics(
                task=match.group("task").strip(),
                iteration=int(match.group("iteration")),
                success=match.group("success") == "True",
                planning_rounds=rounds,
                replanning_count=max(rounds - 1, 0),
                invalid_plan_retries=pending_invalid_plan_retries,
                cumulative_success_rate=float(match.group("rate")),
            )
        )
        pending_invalid_plan_retries = 0
    return LegacyRunMetrics(
        episodes=episodes,
        wall_clock_seconds=float(wall_clock_seconds),
        return_code=int(return_code),
    )
