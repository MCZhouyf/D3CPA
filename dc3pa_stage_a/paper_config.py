"""Frozen Option-B paper run configuration.

Option B keeps the scripted low-level execution substitute in the controller but
switches off the two planner-layer task-specific paths, because those substitute
for the mechanism the paper claims rather than for the missing low-level
interface.

The separation is achievable with environment variables alone:

===========================================  ===========  ==========================
path                                          layer        Option-B state
===========================================  ===========  ==========================
planner._inject_prerequisite_steps            planning     OFF   (LEGACY=0)
run_agent._fixed_workflow_for_task            planning     OFF   (LEGACY=0)
controller deep-mining resource fallback      execution    ON    (BOUNDED=1)
===========================================  ===========  ==========================

``controller._is_deep_mining_task`` returns True when the task is in the
deep-mining set AND (``legacy_task_hacks_enabled()`` OR the bounded fallback
flag), so LEGACY=0 with BOUNDED=1 yields exactly the split above.

Nothing in this module changes behaviour; it records the configuration, asserts
its internal consistency, and produces a stable hash that every run manifest
must carry.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping


RUNTIME_MODES = ("mp5_legacy", "reasoning_only", "dc3pa")
MEMORY_MODES = ("acquire", "calibrate", "evaluate_readonly", "disabled")

#: Environment variables that define the Option-B split. Values are strings so
#: the recorded configuration matches exactly what the process will read.
OPTION_B_ENV: Dict[str, str] = {
    "DC3PA_LEGACY_TASK_HACKS": "0",
    "DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK": "1",
}


@dataclass(frozen=True)
class PaperRunConfig:
    """One frozen configuration shared by every formal run."""

    runtime_mode: str
    memory_mode: str
    record_legacy_workflow_memory: bool
    record_multimodal_memory: bool
    max_execution_attempts: int
    env_flags: Dict[str, str] = field(default_factory=lambda: dict(OPTION_B_ENV))
    acquire_seeds: List[int] = field(default_factory=list)
    evaluate_seeds: List[int] = field(default_factory=list)
    notes: str = ""

    # -- validation ----------------------------------------------------------

    def validate(self) -> None:
        if self.runtime_mode not in RUNTIME_MODES:
            raise ValueError(
                f"runtime_mode must be one of {RUNTIME_MODES}, got {self.runtime_mode!r}"
            )
        if self.memory_mode not in MEMORY_MODES:
            raise ValueError(
                f"memory_mode must be one of {MEMORY_MODES}, got {self.memory_mode!r}"
            )
        if isinstance(self.max_execution_attempts, bool) or self.max_execution_attempts <= 0:
            raise ValueError("max_execution_attempts must be a positive integer")

        # Diagnostic runs may use memory_mode="disabled": it needs no frozen
        # snapshot, writes nothing, and is identical across runtime modes, so it
        # is a legitimate symmetric baseline for substitute-scope and symmetry
        # measurement. It must never be used for reported paper results.
        if self.memory_mode == "disabled":
            if self.record_legacy_workflow_memory or self.record_multimodal_memory:
                raise ValueError(
                    "memory_mode='disabled' forbids long-term memory recording"
                )
            if not self.notes.strip():
                raise ValueError(
                    "memory_mode='disabled' is diagnostic only; record why in notes"
                )

        # Evaluation runs must not write long-term memory.
        if self.memory_mode == "evaluate_readonly":
            if self.record_legacy_workflow_memory or self.record_multimodal_memory:
                raise ValueError(
                    "evaluate_readonly forbids long-term memory recording; set both "
                    "record_legacy_workflow_memory and record_multimodal_memory to False"
                )

        # Option-B split: planner-layer paths off, controller fallback on.
        legacy = self.env_flags.get("DC3PA_LEGACY_TASK_HACKS")
        bounded = self.env_flags.get("DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK")
        if legacy is None or bounded is None:
            raise ValueError(
                "env_flags must pin both DC3PA_LEGACY_TASK_HACKS and "
                "DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK"
            )
        if legacy != "0":
            raise ValueError(
                "Option B requires DC3PA_LEGACY_TASK_HACKS=0 so the planner-layer "
                "task-specific paths (_inject_prerequisite_steps, "
                "_fixed_workflow_for_task) are disabled"
            )
        if bounded != "1":
            raise ValueError(
                "Option B requires DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK=1 so the "
                "declared low-level execution substitute stays active"
            )

        overlap = set(self.acquire_seeds) & set(self.evaluate_seeds)
        if overlap:
            raise ValueError(f"acquire and evaluate seeds overlap: {sorted(overlap)}")

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["acquire_seeds"] = sorted(self.acquire_seeds)
        payload["evaluate_seeds"] = sorted(self.evaluate_seeds)
        payload["env_flags"] = dict(sorted(self.env_flags.items()))
        return payload

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, indent=2)

    def config_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def write(self, path: str | Path) -> str:
        """Validate, write to ``path``, and return the config hash."""
        self.validate()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.canonical_json() + "\n", encoding="utf-8")
        return self.config_hash()

    # -- runtime helpers -----------------------------------------------------

    def export_env(self, environ: Dict[str, str] | None = None) -> Dict[str, str]:
        """Apply the pinned flags to ``environ`` (defaults to ``os.environ``)."""
        self.validate()
        target = os.environ if environ is None else environ
        for key, value in self.env_flags.items():
            target[key] = value
        return dict(self.env_flags)

    def assert_process_matches(self, environ: Mapping[str, str] | None = None) -> None:
        """Fail loudly if the live process does not match the frozen flags."""
        self.validate()
        source = os.environ if environ is None else environ
        mismatched = {
            key: (value, source.get(key))
            for key, value in self.env_flags.items()
            if source.get(key) != value
        }
        if mismatched:
            raise RuntimeError(
                "process environment does not match the frozen paper config: "
                + ", ".join(
                    f"{key}: expected {expected!r}, got {actual!r}"
                    for key, (expected, actual) in sorted(mismatched.items())
                )
            )


def load(path: str | Path) -> PaperRunConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    config = PaperRunConfig(**payload)
    config.validate()
    return config
