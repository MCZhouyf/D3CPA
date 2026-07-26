#!/usr/bin/env python3
"""Read-only Round 5.13E7 semantic audit for the D2 follow-up records."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


EXPECTED_SUMMARY_SHA256 = (
    "8ece520056753a27842f1e67849b6ee50feb6033d8c636b8ac6993ea12b7d306"
)
DEFAULT_D2_ROOT = Path("/external/dc3pa/round513e6d2/91cb7bb")
DEFAULT_D1_ROOT = Path("/external/dc3pa/round513e5/4a6a695c/source-hardening")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON: {path}")
    return payload


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def with_id(payload: dict[str, Any], id_field: str) -> dict[str, Any]:
    item = dict(payload)
    item[id_field] = canonical_sha256(payload)
    return item


def record_without_hash(record: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k != "record_hash"}


def validate_record_hash(record: Mapping[str, Any]) -> bool:
    return record.get("record_hash") == canonical_sha256(record_without_hash(record))


def trace_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            if isinstance(payload, dict):
                events.append(payload)
    return events


def classify_action_boundary(
    *,
    termination_reason: str,
    local_postcondition_success: bool,
    search_budget_exhausted: bool,
    technical_failure: str,
    search_trace_complete: bool,
) -> str:
    if technical_failure:
        return "closed" if search_trace_complete else "unknown"
    if local_postcondition_success or search_budget_exhausted:
        return "closed"
    if termination_reason == "safety_clearance_stop" and search_trace_complete:
        return "closed"
    if termination_reason in {"safety_replan_requested", "recoverable_replan_signal"}:
        return "open"
    return "unknown"


def classify_safety_stop(
    *,
    termination_reason: str,
    search_budget_exhausted: bool,
    technical_failure: str,
    search_trace_complete: bool,
    sensor_complete: bool,
) -> str:
    if technical_failure:
        return "technical_safety_error"
    if not search_trace_complete or not sensor_complete:
        return "evidence_incomplete"
    if termination_reason == "safety_clearance_stop":
        return "final_scientific_safety_stop"
    if search_budget_exhausted or termination_reason == "bounded_search_budget_exhausted":
        return "bounded_search_exhausted"
    if termination_reason in {"safety_replan_requested", "recoverable_replan_signal"}:
        return "recoverable_controller_signal"
    return "evidence_incomplete"


def future_y_action_candidate(
    *,
    action_boundary_closed: str,
    safety_stop_classification: str,
    technical_failure: str,
    sensor_complete: bool,
    observed_postcondition: str,
) -> int | None:
    if (
        action_boundary_closed == "closed"
        and not technical_failure
        and sensor_complete
        and not observed_postcondition
        and safety_stop_classification
        in {"final_scientific_safety_stop", "bounded_search_exhausted"}
    ):
        return 0
    return None


def classify_action_goal_relation(record: Mapping[str, Any]) -> tuple[str, list[str], bool]:
    pre = record["pre"]
    outcome = record["outcome"]
    task = pre["binding"]["task"]
    action = pre["action"]
    subgoal = str(pre.get("subgoal", "")).lower()
    observed = outcome.get("observed_action_postcondition", "")
    goal_progress = outcome.get("y_goal") == 1

    if action == {"name": "find", "args": {"obj": "tree"}} and observed == "minecraft:block/wood":
        if task == "log" and "log" in subgoal:
            return (
                "enabling_subgoal",
                [
                    "planner_subgoal_mentions_logs",
                    "controller_canonical_signature=find:wood",
                    "retrieval_family=minecraft:family/log_source",
                    "local_postcondition=minecraft:block/wood",
                    "terminal_goal_remained_separate:y_goal=0",
                ],
                False,
            )
        if task == "sapling":
            return (
                "unresolved",
                [
                    "planner_subgoal_mentions_saplings",
                    "local_postcondition_observed_only_wood",
                    "frozen_task_asset_goal=sapling",
                    "no_frozen_dependency_path_from_wood_to_sapling_was_bound",
                    "terminal_goal_remained_separate:y_goal=0",
                ],
                False,
            )
    if action == {"name": "find", "args": {"obj": "iron ore"}}:
        return (
            "enabling_subgoal",
            [
                "local_find_postcondition_would_expose_iron_ore_source",
                "terminal_mine_goal_requires_later_tool_or_mine_action",
                "D2_record_observed_no_postcondition",
            ],
            goal_progress,
        )
    return ("unresolved", ["no_policy_rule_matched"], goal_progress)


def _record_for(root: Path, label: str) -> tuple[Path, dict[str, Any]]:
    files = sorted((root / "diagnostic-outputs" / label / "accepted_scientific_action").glob("*.json"))
    if len(files) != 1:
        raise ValueError(f"Expected one accepted D2 record for {label}, found {len(files)}")
    return files[0], load_json(files[0])


def _trace_for(root: Path, label: str) -> Path:
    if label == "00-sapling":
        return root / "traces" / "00-sapling-attempt2.jsonl"
    return root / "traces" / f"{label}.jsonl"


def build_event_chain(label: str, record_path: Path, record: Mapping[str, Any], trace_path: Path) -> dict[str, Any]:
    pre = record["pre"]
    outcome = record["outcome"]
    controller = record["controller"]
    find_obs = controller.get("return_payload", {}).get("post_state_evidence", {}).get("find_observation", {})
    steps = find_obs.get("observation_steps_v2", [])
    events = trace_events(trace_path)
    controller_events = [event["payload"] for event in events if event.get("event_type") == "controller_completed"]
    seed_events = [event["payload"] for event in events if event.get("event_type") == "environment_seed_applied"]
    llm_planning = [
        event for event in events
        if event.get("event_type") == "llm_call_completed"
        and event.get("payload", {}).get("purpose") == "planning"
    ]
    llm_reflection = [
        event for event in events
        if event.get("event_type") == "llm_call_completed"
        and event.get("payload", {}).get("purpose") == "reflection"
    ]
    sensor_complete = all(
        step.get("detector_sensor_status") == "ok"
        and not step.get("sensor_missing")
        and not step.get("sensor_error")
        and not step.get("missing_sensor_fields")
        for step in steps
    )
    payload = {
        "contract_type": "TreeWoodEventChainAudit" if label in {"00-sapling", "02-log"} else "IronOreSafetyEventChainAudit",
        "assignment": label,
        "record_path": str(record_path),
        "record_sha256": file_sha256(record_path),
        "record_hash_valid": validate_record_hash(record),
        "terminal_task_name": pre["binding"]["terminal_task"],
        "terminal_task_runtime_name": pre["binding"]["task"],
        "planner_local_subgoal": pre.get("subgoal", ""),
        "planner_raw_action": pre["action"],
        "controller_canonical_action_object": pre.get("controller_canonical_signature", ""),
        "retrieval_canonical_signature": pre.get("retrieval_canonical_signature", ""),
        "outcome_target_canonical_identity": pre.get("outcome_target_canonical_identity", ""),
        "expected_local_postcondition": outcome.get("expected_action_postcondition", ""),
        "observed_local_postcondition": outcome.get("observed_action_postcondition", ""),
        "controller_status": outcome.get("controller_status", ""),
        "controller_terminal_reason": outcome.get("controller_terminal_reason", ""),
        "controller_event": controller_events[-1] if controller_events else {},
        "y_action": outcome.get("y_action"),
        "y_action_evidence_status": outcome.get("y_action_evidence_status", ""),
        "y_goal": outcome.get("y_goal"),
        "y_goal_evidence_status": outcome.get("y_goal_evidence_status", ""),
        "search_trace_complete": bool(find_obs.get("search_trace_complete", False)),
        "search_budget_exhausted": bool(find_obs.get("search_budget_exhausted", False)),
        "frozen_search_budget": find_obs.get("frozen_search_budget"),
        "search_steps_consumed": find_obs.get("search_steps_consumed"),
        "search_seconds_consumed": find_obs.get("search_seconds_consumed"),
        "observation_step_count": len(steps),
        "sensor_complete": sensor_complete,
        "target_directly_observed": bool(find_obs.get("target_visible", False)),
        "matched_candidate_id": find_obs.get("matched_candidate_id", ""),
        "technical_failure": find_obs.get("technical_failure", ""),
        "seed_event": seed_events[-1] if seed_events else {},
        "planning_call_count": len(llm_planning),
        "reflection_call_count": len(llm_reflection),
        "evaluation_before_action_calls": pre.get("evaluation_before_action_calls", 0),
        "memory_write_count": pre.get("memory_write_count", 0),
        "acquisition_write_count": pre.get("acquisition_write_count", 0),
    }
    return with_id(payload, "audit_id")


def build_input_integrity(
    *, repo: Path, d2_root: Path, d1_root: Path, summary: Mapping[str, Any]
) -> dict[str, Any]:
    e7_audit_source = git(repo, "rev-parse", "HEAD")
    status = git(repo, "status", "--porcelain")
    closeout = d2_root / "D2_FOLLOWUP_CLOSEOUT.md"
    closure = load_json(d2_root / "execution-closure" / "execution_closure_manifest.json")
    runtime = load_json(d2_root / "source-hardening" / "round513e6d2_runtime_release.json")
    assignments = load_json(d2_root / "source-hardening" / "d2_paired_assignments.json")
    seal = load_json(d2_root / "source-hardening" / "d2_paired_assignment_seal.json")
    auth = load_json(d2_root / "source-hardening" / "round513e6d2_diagnostic_authorization_input.json")
    receipt = load_json(d2_root / "execution-closure" / "d2_authorization_receipt_r1.json")
    d1_summary = load_json(d1_root / "execution-closure" / "d1_diagnostic_result_summary.json")
    record_rows = []
    for label in ("00-sapling", "01-iron_ore", "02-log"):
        path, record = _record_for(d2_root, label)
        record_rows.append({
            "assignment": label,
            "record_path": str(path),
            "record_sha256": file_sha256(path),
            "record_hash": record.get("record_hash", ""),
            "record_hash_valid": validate_record_hash(record),
            "source_commit": record["pre"]["binding"]["source_commit"],
            "task": record["pre"]["binding"]["task"],
            "terminal_task": record["pre"]["binding"]["terminal_task"],
            "seed_commitment": record["pre"]["binding"]["seed_commitment"],
        })
    d2_record_sources = {row["source_commit"] for row in record_rows}
    d2_sources_match = (
        len(d2_record_sources) == 1
        and summary["source_commit"]
        == runtime["source_commit"]
        == closure["source_commit"]
        == next(iter(d2_record_sources))
    )
    payload = {
        "contract_type": "Round513D2FollowupInputIntegrityAudit",
        "e7_audit_source_commit_from_git": e7_audit_source,
        "git_worktree_clean": status == "",
        "d2_execution_source_commit": summary["source_commit"],
        "source_commit_from_summary": summary["source_commit"],
        "source_commit_from_runtime": runtime["source_commit"],
        "source_commit_from_closure": closure["source_commit"],
        "source_commit_from_records": sorted(d2_record_sources),
        "summary_sha256": file_sha256(d2_root / "D2_FOLLOWUP_RESULT_SUMMARY.json"),
        "closeout_sha256": file_sha256(closeout),
        "summary_id": canonical_sha256(summary),
        "authorization_input_id": auth["authorization_input_id"],
        "authorization_receipt_id": receipt["receipt_id"],
        "execution_closure_manifest_id": closure["manifest_id"],
        "assignment_seal_id": seal["seal_id"],
        "assignments_id": assignments["assignments_id"],
        "runtime_release_id": runtime["release_id"],
        "d1_parent_result_id": d1_summary["report_id"],
        "d1_parent_source_commit": d1_summary["source_commit"],
        "task_seed_order": [
            {
                "order": row["order"],
                "formal_task": row["formal_task"],
                "runtime_task": row["runtime_task"],
                "seed_commitment": row["seed_commitment"],
                "task_asset": row["task_asset"],
                "task_asset_sha256": row["task_asset_sha256"],
            }
            for row in assignments["rows"]
        ],
        "planner_schema_id": runtime["planner_schema_id"],
        "planner_prompt_id": runtime["planner_prompt_id"],
        "planner_parser_id": runtime["planner_parser_id"],
        "controller_id": runtime["controller_id"],
        "evaluator_id": runtime["evaluator_id"],
        "memory_release_id": runtime["paper_memory_release_id"],
        "scene_exemplar_release_id": runtime["scene_exemplar_release_id"],
        "mineclip_policy_id": runtime["mineclip_policy_id"],
        "outcome_schema_id": runtime["outcome_schema_id"],
        "signature_registry_id": runtime["signature_registry_id"],
        "safety_policy_id": runtime["safety_policy_id"],
        "technical_retry_policy_id": runtime["technical_retry_policy_id"],
        "process_cleanup_policy_id": runtime["process_cleanup_policy_id"],
        "record_rows": record_rows,
        "original_records_mutated": False,
        "provider_or_minedojo_launch_count_this_round": 0,
    }
    payload["cross_validation_passed"] = (
        payload["git_worktree_clean"]
        and d2_sources_match
        and payload["summary_sha256"] == EXPECTED_SUMMARY_SHA256
        and all(row["record_hash_valid"] for row in record_rows)
    )
    return with_id(payload, "audit_id")


def build_tree_semantic_audit(tree_chains: list[Mapping[str, Any]], records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    rows = []
    unresolved = False
    for chain in tree_chains:
        label = str(chain["assignment"])
        relation, evidence, goal_progress = classify_action_goal_relation(records[label])
        if relation == "unresolved":
            unresolved = True
        rows.append({
            "assignment": label,
            "terminal_task_name": chain["terminal_task_name"],
            "relation_classification": relation,
            "evidence_chain": evidence,
            "counterexample_checks": {
                "tree_not_equated_to_sapling": chain["terminal_task_name"] != "sapling"
                or chain["observed_local_postcondition"] != "minecraft:block/sapling",
                "tree_not_equated_to_log_item": chain["outcome_target_canonical_identity"] != "minecraft:item/log",
                "action_and_goal_labels_remain_orthogonal": (
                    chain["y_action"],
                    chain["y_goal"],
                ) in {(1, 0), (None, 0), (None, 1)},
            },
            "goal_progress_evidence": goal_progress,
            "retain_original_y_action": chain["y_action"],
            "retain_original_y_goal": chain["y_goal"],
        })
    payload = {
        "contract_type": "TreeWoodSemanticBoundaryAudit",
        "schema_version": 1,
        "rows": rows,
        "overall_relation_classification": "unresolved" if unresolved else "enabling_subgoal",
        "source_fix_required": unresolved,
        "real_diagnostic_replay_required": unresolved,
        "historical_labels_remain_unchanged": True,
        "conclusion": (
            "log tree->wood is a valid enabling subgoal, but sapling tree->wood "
            "is not uniquely closed by frozen dependency evidence."
        ),
    }
    return with_id(payload, "audit_id")


def build_iron_safety_audit(chain: Mapping[str, Any]) -> dict[str, Any]:
    action_boundary = classify_action_boundary(
        termination_reason=str(chain["controller_terminal_reason"]),
        local_postcondition_success=bool(chain["observed_local_postcondition"]),
        search_budget_exhausted=bool(chain["search_budget_exhausted"]),
        technical_failure=str(chain["technical_failure"]),
        search_trace_complete=bool(chain["search_trace_complete"]),
    )
    stop_class = classify_safety_stop(
        termination_reason=str(chain["controller_terminal_reason"]),
        search_budget_exhausted=bool(chain["search_budget_exhausted"]),
        technical_failure=str(chain["technical_failure"]),
        search_trace_complete=bool(chain["search_trace_complete"]),
        sensor_complete=bool(chain["sensor_complete"]),
    )
    future_label = future_y_action_candidate(
        action_boundary_closed=action_boundary,
        safety_stop_classification=stop_class,
        technical_failure=str(chain["technical_failure"]),
        sensor_complete=bool(chain["sensor_complete"]),
        observed_postcondition=str(chain["observed_local_postcondition"]),
    )
    payload = {
        "contract_type": "IronOreSafetyBoundedSearchAudit",
        "assignment": chain["assignment"],
        "action_boundary_closed": action_boundary == "closed",
        "action_boundary_closed_state": action_boundary,
        "safety_stop_classification": stop_class,
        "future_y_action_candidate": future_label,
        "historical_y_action": chain["y_action"],
        "historical_y_goal": chain["y_goal"],
        "policy_counterfactual_adjudication": {
            "permitted_to_override_historical_record": False,
            "if_v3_policy_applied_prospectively": {
                "y_action": future_label,
                "reason": "final safety stop with complete sensors and absent postcondition",
            },
        },
        "evidence": {
            "termination_reason": chain["controller_terminal_reason"],
            "search_trace_complete": chain["search_trace_complete"],
            "search_budget_exhausted": chain["search_budget_exhausted"],
            "frozen_search_budget": chain["frozen_search_budget"],
            "search_steps_consumed": chain["search_steps_consumed"],
            "observation_step_count": chain["observation_step_count"],
            "sensor_complete": chain["sensor_complete"],
            "target_directly_observed": chain["target_directly_observed"],
            "technical_failure": chain["technical_failure"],
        },
        "historical_labels_remain_unchanged": True,
    }
    return with_id(payload, "audit_id")


def build_action_goal_policy(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    rows = []
    for label, record in records.items():
        relation, evidence, goal_progress = classify_action_goal_relation(record)
        pre = record["pre"]
        outcome = record["outcome"]
        rows.append({
            "assignment": label,
            "terminal_goal_predicate": pre["binding"]["terminal_task"],
            "local_action_postcondition": outcome.get("expected_action_postcondition", ""),
            "action_goal_relation": relation,
            "dependency_path_evidence": evidence,
            "goal_progress_evidence": goal_progress,
            "does_not_modify_y_action": True,
            "does_not_modify_y_goal": True,
        })
    payload = {
        "contract_type": "ActionGoalRelationPolicyCandidateV1",
        "schema_version": 1,
        "primary_label": "y_action",
        "terminal_label": "y_goal",
        "relation_interpretation_only": True,
        "rows": rows,
        "not_a_chrm_training_label": True,
    }
    return with_id(payload, "policy_id")


def build_safety_policy_candidate(iron_audit: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "contract_type": "SafetyTerminationLabelPolicyCandidateV3",
        "schema_version": 1,
        "candidate": "I1",
        "historical_relabel_permitted": False,
        "prospective_rule": {
            "action_boundary_closed_required": True,
            "technical_failure_required_absent": True,
            "sensor_and_postcondition_evidence_required_complete": True,
            "allowed_terminal_reasons": [
                "final_scientific_safety_stop",
                "bounded_search_exhausted",
            ],
            "absent_local_postcondition_future_y_action": 0,
        },
        "iron_ore_counterfactual": iron_audit["policy_counterfactual_adjudication"],
        "does_not_override_d2": True,
    }
    return with_id(payload, "policy_id")


def choose_go_no_go(tree_semantic: Mapping[str, Any], iron_audit: Mapping[str, Any]) -> str:
    tree_closed = tree_semantic["overall_relation_classification"] != "unresolved"
    iron_closed = bool(iron_audit["action_boundary_closed"])
    if tree_closed and iron_closed:
        return "G0"
    if tree_closed and not iron_closed:
        return "G1"
    if not tree_closed and not iron_closed:
        return "G2"
    return "G3"


def build_decision_input(tree_semantic: Mapping[str, Any], iron_audit: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "contract_type": "Round513D3SemanticDecisionInput",
        "schema_version": 1,
        "reason": "Tree/Wood task semantics are not uniquely determined for sapling from frozen dependency evidence.",
        "tree_wood_candidates": [
            {
                "option": "T1",
                "meaning": "legal enabling_subgoal; retain y_action=1,y_goal=0",
                "chrm_consistency": "consistent only where dependency path is frozen",
                "label_noise_risk": "medium for sapling if accepted without dependency proof",
                "formal_collection_impact": "permits tree probes as positive actions",
                "requires_new_minedojo_diagnostic": False,
            },
            {
                "option": "T2",
                "meaning": "Planner/Signature misalignment; repair before replay",
                "chrm_consistency": "avoids proxy positives",
                "label_noise_risk": "low after repair",
                "formal_collection_impact": "requires source hardening before collection",
                "requires_new_minedojo_diagnostic": True,
            },
            {
                "option": "T3",
                "meaning": "evidence insufficient; keep unresolved and run D3 tree diagnostic",
                "chrm_consistency": "fail-closed",
                "label_noise_risk": "low",
                "formal_collection_impact": "delays tree-family inclusion",
                "requires_new_minedojo_diagnostic": True,
            },
        ],
        "iron_ore_candidates": [
            {
                "option": "I1",
                "meaning": "final legal safety stop plus absent postcondition -> future y_action=0",
                "chrm_consistency": "consistent with D2 SafetyTerminationPolicyV2",
                "label_noise_risk": "low when sensors are complete",
                "formal_collection_impact": "allows prospective safety-stop negatives",
                "requires_new_minedojo_diagnostic": False,
            },
            {
                "option": "I2",
                "meaning": "only bounded budget exhaustion can be y_action=0; safety stop remains null",
                "chrm_consistency": "more conservative than current D2 policy",
                "label_noise_risk": "low but underuses complete safety evidence",
                "formal_collection_impact": "more ambiguous records",
                "requires_new_minedojo_diagnostic": False,
            },
            {
                "option": "I3",
                "meaning": "define labels by action family and stop subtype",
                "chrm_consistency": "explicit and extensible",
                "label_noise_risk": "low if subtype taxonomy is frozen",
                "formal_collection_impact": "requires policy expansion",
                "requires_new_minedojo_diagnostic": False,
            },
            {
                "option": "I4",
                "meaning": "evidence insufficient; add observation fields before diagnosis",
                "chrm_consistency": "fail-closed",
                "label_noise_risk": "lowest but delays use",
                "formal_collection_impact": "requires D3 instrumentation",
                "requires_new_minedojo_diagnostic": True,
            },
        ],
        "tree_semantic_audit_id": tree_semantic["audit_id"],
        "iron_safety_audit_id": iron_audit["audit_id"],
        "automatic_approval": False,
    }
    return with_id(payload, "decision_input_id")


def build_go_no_go(
    tree_semantic: Mapping[str, Any],
    iron_audit: Mapping[str, Any],
    decision_input: Mapping[str, Any] | None,
) -> dict[str, Any]:
    status = choose_go_no_go(tree_semantic, iron_audit)
    payload = {
        "contract_type": "Round513D3GoNoGoDecision",
        "schema_version": 1,
        "status": status,
        "meaning": {
            "G0": "NO_NEW_DIAGNOSTIC_POLICY_ONLY",
            "G1": "D3_IRON_ONLY",
            "G2": "D3_TREE_IRON",
            "G3": "BLOCKED_AUTHOR_DECISION",
        }[status],
        "tree_wood_closed": tree_semantic["overall_relation_classification"] != "unresolved",
        "iron_ore_closed": bool(iron_audit["action_boundary_closed"]),
        "reason": (
            "sapling tree->wood relation lacks unique frozen dependency support"
            if status == "G3"
            else "deterministic rule outcome"
        ),
        "decision_input_id": decision_input.get("decision_input_id", "") if decision_input else "",
        "d3_blueprint_created": False,
        "d3_assignments_created": False,
        "d3_seal_created": False,
        "d3_authorization_created": False,
        "minedojo_launch_count": 0,
        "provider_launch_count": 0,
    }
    return with_id(payload, "decision_id")


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite {path}")
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_audit(*, repo: Path, d2_root: Path, d1_root: Path, output_root: Path) -> dict[str, Any]:
    summary_path = d2_root / "D2_FOLLOWUP_RESULT_SUMMARY.json"
    if file_sha256(summary_path) != EXPECTED_SUMMARY_SHA256:
        raise ValueError("D2 follow-up summary SHA-256 mismatch")
    summary = load_json(summary_path)
    records: dict[str, dict[str, Any]] = {}
    record_paths: dict[str, Path] = {}
    for label in ("00-sapling", "01-iron_ore", "02-log"):
        record_paths[label], records[label] = _record_for(d2_root, label)
    integrity = build_input_integrity(repo=repo, d2_root=d2_root, d1_root=d1_root, summary=summary)
    if not integrity["cross_validation_passed"]:
        raise ValueError("D2 follow-up input integrity audit failed")
    chains = {
        label: build_event_chain(label, record_paths[label], records[label], _trace_for(d2_root, label))
        for label in ("00-sapling", "01-iron_ore", "02-log")
    }
    tree_semantic = build_tree_semantic_audit(
        [chains["00-sapling"], chains["02-log"]], records
    )
    iron_safety = build_iron_safety_audit(chains["01-iron_ore"])
    action_goal_policy = build_action_goal_policy(records)
    safety_policy = build_safety_policy_candidate(iron_safety)
    decision_input = None
    if choose_go_no_go(tree_semantic, iron_safety) == "G3":
        decision_input = build_decision_input(tree_semantic, iron_safety)
    go_no_go = build_go_no_go(tree_semantic, iron_safety, decision_input)
    objects: list[tuple[str, Mapping[str, Any]]] = [
        ("round513_d2_followup_input_integrity_audit.json", integrity),
        ("treewood_event_chain_audit.json", {
            "contract_type": "TreeWoodEventChainAuditCollection",
            "rows": [chains["00-sapling"], chains["02-log"]],
            "audit_id": canonical_sha256([chains["00-sapling"]["audit_id"], chains["02-log"]["audit_id"]]),
        }),
        ("ironore_safety_event_chain_audit.json", chains["01-iron_ore"]),
        ("treewood_semantic_boundary_audit.json", tree_semantic),
        ("ironore_safety_bounded_search_audit.json", iron_safety),
        ("action_goal_relation_policy_candidate_v1.json", action_goal_policy),
        ("safety_termination_label_policy_candidate_v3.json", safety_policy),
        ("round513_d3_go_no_go_decision.json", go_no_go),
    ]
    if decision_input:
        objects.append(("round513_d3_semantic_decision_input.json", decision_input))
    manifest_rows = []
    for filename, payload in objects:
        path = output_root / filename
        write_json(path, payload)
        manifest_rows.append({
            "filename": filename,
            "file_sha256": file_sha256(path),
            "object_id": (
                payload.get("audit_id")
                or payload.get("policy_id")
                or payload.get("decision_id")
                or payload.get("decision_input_id")
            ),
            "contract_type": payload.get("contract_type"),
        })
    manifest = with_id({
        "contract_type": "Round513E7SemanticAuditManifest",
        "e7_audit_source_commit": git(repo, "rev-parse", "HEAD"),
        "d2_execution_source_commit": summary["source_commit"],
        "d2_summary_sha256": EXPECTED_SUMMARY_SHA256,
        "output_object_count": len(manifest_rows),
        "provider_launch_count": 0,
        "minedojo_launch_count": 0,
        "created_no_d3_assignments": True,
        "created_no_d3_seal": True,
        "created_no_d3_authorization": True,
        "rows": manifest_rows,
    }, "manifest_id")
    write_json(output_root / "manifest.json", manifest)
    return {
        "manifest": manifest,
        "objects": {name: payload for name, payload in objects},
        "output_root": str(output_root),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument("--d2-root", type=Path, default=DEFAULT_D2_ROOT)
    parser.add_argument("--d1-root", type=Path, default=DEFAULT_D1_ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.output_root.exists() and any(args.output_root.iterdir()):
        raise ValueError("E7 output root must be empty")
    result = run_audit(
        repo=args.repo_root.resolve(),
        d2_root=args.d2_root.resolve(),
        d1_root=args.d1_root.resolve(),
        output_root=args.output_root.resolve(),
    )
    print(json.dumps({
        "output_root": result["output_root"],
        "manifest_id": result["manifest"]["manifest_id"],
        "minedojo_launch_count": 0,
        "provider_launch_count": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
