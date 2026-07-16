"""Git-backed protected identity audit for the Round 5.10 source extension."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable


PROTECTED_GROUPS = {
    "prompt_hash_bundle": (
        "MP5_agent/agent/prompts/prompt_template.txt",
        "MP5_agent/agent/prompts/task_prompt.txt",
        "MP5_agent/agent/reflexion.py",
        "MP5_agent/agent/work_memory.py",
        "MP5_agent/dc3pa/evaluation/chain.py",
        "MP5_agent/dc3pa/reliability/ordinal_confidence.py",
    ),
    "controller": (
        "MP5_agent/agent/controller.py",
        "MP5_agent/agent/structured_actions.py",
    ),
    "evaluator": ("MP5_agent/agent/run_agent.py",),
}


def _canonical_sha(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout


def _blob_sha(repo: Path, commit: str, path: str) -> str:
    return hashlib.sha256(_git(repo, "show", f"{commit}:{path}")).hexdigest()


def _group_identity(repo: Path, commit: str, paths: Iterable[str]) -> str:
    return _canonical_sha(
        {path: _blob_sha(repo, commit, path) for path in sorted(paths)}
    )


def _tree_identity(repo: Path, commit: str, path: str) -> str:
    rows = _git(repo, "ls-tree", "-r", commit, "--", path).decode().splitlines()
    return _canonical_sha(sorted(rows))


def audit_source_extension(
    *,
    repo_root: str | Path,
    parent_commit: str,
    final_commit: str,
    approval: dict[str, Any],
    authorization: dict[str, Any],
    schedule: dict[str, Any],
    policy: dict[str, Any],
    amendment: dict[str, Any],
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    identities: dict[str, dict[str, str]] = {}
    for name, paths in PROTECTED_GROUPS.items():
        identities[name] = {
            "before": _group_identity(repo, parent_commit, paths),
            "after": _group_identity(repo, final_commit, paths),
        }
    identities["task_catalog"] = {
        "before": _tree_identity(repo, parent_commit, "MP5_agent/agent/tasks"),
        "after": _tree_identity(repo, final_commit, "MP5_agent/agent/tasks"),
    }
    changed = [
        name for name, values in identities.items()
        if values["before"] != values["after"]
    ]
    external_errors = []
    expected_external = {
        "approval parent": (
            approval.get("parent_source_commit"), parent_commit
        ),
        "authorization parent": (
            authorization.get("source_commit"), parent_commit
        ),
        "authorization schedule": (
            authorization.get("acquisition_schedule_id"), schedule.get("schedule_id")
        ),
        "authorization policy": (
            authorization.get("bootstrap_policy_id"), policy.get("policy_id")
        ),
        "authorization amendment": (
            authorization.get("bootstrap_amendment_id"), amendment.get("amendment_id")
        ),
    }
    for label, (actual, expected) in expected_external.items():
        if actual != expected:
            external_errors.append(label)
    if changed or external_errors:
        raise ValueError(
            "protected source extension audit failed: "
            f"changed={changed}, external={external_errors}"
        )
    return {
        "schema_version": 1,
        "parent_source_commit": parent_commit,
        "new_source_commit": final_commit,
        "protected_identities": identities,
        "schedule_id": str(schedule["schedule_id"]),
        "bootstrap_policy_id": str(policy["policy_id"]),
        "bootstrap_amendment_id": str(amendment["amendment_id"]),
        "eligible": True,
        "errors": [],
    }
