"""Guard protected experiment semantics across Round 5.8 schema migration."""

from __future__ import annotations
import hashlib, json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
EXPECTED_NEW_SCHEMA = 2
EXPECTED_MODEL = "gpt-5.1"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def records(items: Sequence[Mapping[str, Any]], fields: Sequence[str]):
    return sorted(
        ({field: item.get(field) for field in fields} for item in items),
        key=lambda item: tuple(str(item.get(field, "")) for field in fields),
    )


def policy_without_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("policy_id", None)
    result.pop("schema_version", None)
    return result


def semantic_view(payload: Mapping[str, Any]) -> dict[str, Any]:
    config = dict(payload.get("config", {}))
    final = dict(payload.get("final_test_exclusion", {}))
    final_tasks = []
    for item in final.get("tasks", []):
        metadata = dict(item.get("metadata", {}))
        final_tasks.append({
            "task": item.get("task"),
            "difficulty": item.get("difficulty"),
            "goal_status": item.get("goal_status"),
            "test_seeds": list(item.get("test_seeds", [])),
            "minimum_subgoals": metadata.get("minimum_subgoals"),
        })
    budget_fields = (
        "phase", "maximum_episodes", "maximum_high_level_steps_per_episode",
        "maximum_llm_calls_per_episode", "maximum_replans_per_episode",
        "timeout_seconds_per_episode", "temperature", "top_p",
    )
    return {
        "config": {key: config.get(key) for key in (
            "split_salt", "final_seed_salt", "acquisition_seed_salt",
            "development_seed_salt", "role_salt", "final_seed_count",
            "acquisition_seeds_per_covered_task",
            "development_seeds_per_task",
        )},
        "task_catalog": records(payload.get("task_catalog", []),
                                ("task", "difficulty", "minimum_subgoals")),
        "final_tasks": sorted(final_tasks,
                              key=lambda x: (str(x["difficulty"]), str(x["task"]))),
        "acquisition": records(payload.get("acquisition_assignments", []), (
            "group_id", "task", "seed", "task_kind", "difficulty",
            "sequence_index",
        )),
        "development": records(payload.get("development_assignments", []), (
            "group_id", "task", "seed", "role", "difficulty", "goal_status",
        )),
        "budgets": records(payload.get("phase_budgets", []), budget_fields),
        "environment_grid": dict(payload.get("environment_search_space", {})),
        "activation_policy": policy_without_identity(
            payload.get("activation_policy", {})
        ),
        "sufficiency_policy": dict(payload.get("data_sufficiency_policy", {})),
        "dry_run_group_ids": sorted(payload.get("dry_run_group_ids", [])),
    }


@dataclass(frozen=True)
class SemanticMigrationReport:
    old_design_id: str
    new_design_id: str
    old_schema: int
    new_schema: int
    old_semantic_sha256: str
    new_semantic_sha256: str
    protected_semantics_equal: bool
    new_model_id: str
    mutable_alias_approved: bool
    eligible: bool
    reasons: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    report_id: str = ""

    def payload(self):
        value = asdict(self)
        value.pop("report_id", None)
        value["reasons"] = list(self.reasons)
        return value

    def compute_id(self):
        return digest(self.payload())

    def with_id(self):
        return replace(self, report_id=self.compute_id())

    def to_dict(self):
        value = self.payload()
        value["report_id"] = self.report_id or self.compute_id()
        return value


@dataclass(frozen=True)
class Round59ApprovalBinding:
    blueprint_id: str
    approval_record_id: str
    approved_blueprint_content_sha256: str
    migration_report_id: str
    reference_design_id: str
    mutable_alias_risk_acknowledged: bool
    model_epoch_policy_version: str
    interleaved_schedule_policy_version: str
    interleaved_schedule_salt: str
    schema_version: int = 1
    binding_id: str = ""

    def __post_init__(self):
        required = (
            self.blueprint_id, self.approval_record_id,
            self.approved_blueprint_content_sha256, self.migration_report_id,
            self.reference_design_id, self.model_epoch_policy_version,
            self.interleaved_schedule_policy_version,
            self.interleaved_schedule_salt,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Round 5.9 approval binding is incomplete")
        if not self.mutable_alias_risk_acknowledged:
            raise ValueError("gpt-5.1 mutable-alias risk must be acknowledged")
        expected = self.compute_id()
        if self.binding_id and self.binding_id != expected:
            raise ValueError("Approval binding hash mismatch")

    def payload(self):
        value = asdict(self)
        value.pop("binding_id", None)
        return value

    def compute_id(self):
        return digest(self.payload())

    def with_id(self):
        return replace(self, binding_id=self.compute_id())

    def to_dict(self):
        value = self.payload()
        value["binding_id"] = self.binding_id or self.compute_id()
        return value


def compare_designs(old: Mapping[str, Any],
                    new: Mapping[str, Any]) -> SemanticMigrationReport:
    old_hash = digest(semantic_view(old))
    new_hash = digest(semantic_view(new))
    config = dict(new.get("config", {}))
    profile = dict(new.get("model_profile", {}))
    model = str(config.get("model_id", profile.get("model", "")))
    alias_approved = bool(profile.get("mutable_alias_author_approved", False))
    reasons = []
    if int(new.get("schema_version", 0)) != EXPECTED_NEW_SCHEMA:
        reasons.append("new reference design is not schema v2")
    if model != EXPECTED_MODEL:
        reasons.append("new model is not gpt-5.1")
    if not alias_approved:
        reasons.append("mutable alias approval is missing")
    if old_hash != new_hash:
        reasons.append("protected experiment semantics changed")
    if int(old.get("schema_version", 0)) != 1:
        reasons.append("old reference design is not schema v1")
    if not str(old.get("design_id", "")).strip() or not str(
        new.get("design_id", "")
    ).strip():
        reasons.append("design identity is missing")
    if old.get("design_id") == new.get("design_id"):
        reasons.append("schema migration must create a new design identity")
    return SemanticMigrationReport(
        old_design_id=str(old.get("design_id", "")),
        new_design_id=str(new.get("design_id", "")),
        old_schema=int(old.get("schema_version", 0)),
        new_schema=int(new.get("schema_version", 0)),
        old_semantic_sha256=old_hash,
        new_semantic_sha256=new_hash,
        protected_semantics_equal=old_hash == new_hash,
        new_model_id=model,
        mutable_alias_approved=alias_approved,
        eligible=not reasons,
        reasons=tuple(reasons),
    ).with_id()


def load_json(path: str | Path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Design JSON must contain an object")
    return value
