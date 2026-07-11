from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

from ..contracts import Plan
from ..errors import MemoryInvariantError
from .multimodal_memory import MultimodalMemory, SuccessfulEpisode


def import_legacy_workflows(
    memory: MultimodalMemory,
    workflow_json_path: str | Path,
    source_label: str = "legacy_work_memory",
    confirmed_success: bool = False,
) -> List[Dict[str, Any]]:
    """Warm-start dependency edges from legacy *successful* workflow records.

    No scene exemplar is fabricated because the legacy JSON does not contain reliable
    paired observations.
    """

    if not confirmed_success:
        raise MemoryInvariantError(
            "Legacy import requires confirmed_success=True after verifying that every "
            "record came from a completed successful task"
        )
    path = Path(workflow_json_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Legacy workflow file must contain an object keyed by task name")
    results = []
    for task_name, record in payload.items():
        if isinstance(record, Mapping):
            workflow = record.get("successful_workflow", record.get("workflow"))
        else:
            workflow = record
        if not workflow:
            continue
        plan = Plan.from_dict({"workflow": workflow}, task=str(task_name))
        episode = SuccessfulEpisode(
            task_name=str(task_name),
            plan=plan,
            scenes=(),
            metadata={"source": source_label, "source_file": str(path)},
        )
        results.append(memory.record_success(episode))
    return results
