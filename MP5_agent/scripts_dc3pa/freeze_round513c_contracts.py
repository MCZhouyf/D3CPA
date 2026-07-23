#!/usr/bin/env python3
"""Freeze the outcome-free Round 5.13C contracts outside the repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from dc3pa.experiments.round513_collection import build_collection_contracts


ROOT = Path(__file__).resolve().parents[1]
METHOD_CONTRACT_ID = "ee6cd6d6199c5bb401d8ea0114338a7f7ac18a92c16b6a0413c4967d8c106fdf"
HISTORICAL_DATA_DECISION_ID = "82de675a8f9b37cfdb06f7d74f75b2b6e9b55561bf5299a7b1f6c2da9f429e89"
DEPENDENCY_SCHEMA_ID = "2ae914b777625059ab8f91d92b0c46caee5182758f78889102ee2c8f1ba8aa31"
MEMORY_V5_RELEASE_ID = "cc2310aeb60f63e6a1896a4c05109a1ec391649ce102e11b65b6343605789813"
SCENE_RELEASE_ID = "ef05d5e19158dc1e203f07235286610d48961f4b25d52a4477ed2af266002f49"
MINECLIP_POLICY_ID = "a121693c50ca84f12239dbb028747eeb22f25b24f7a66e88bbd6135d9e70d51"
PARAMETER_PROVENANCE_ID = "b777e452fb52d965a927cfbf14ad878cc86204fef075aabcb902eb5ba56aee27"

CONTRACT_NAMES = (
    "chrmlite_development_collection_authorization",
    "chrmlite_development_collection_blueprint",
    "chrmlite_development_seed_namespace",
    "chrmlite_rule_type_registry_v4_1",
    "chrmlite_planner_output_schema_v4_1",
    "chrmlite_bilateral_retrieval_policy_v4_1",
    "chrmlite_step_outcome_registry_v4_1",
    "chrmlite_decision_record_schema_v4_1",
    "chrmlite_collection_exclusion_registry",
    "chrmlite_support_and_degradation_policy",
    "chrmlite_engineering_smoke_design",
    "cdt_replay_feasibility_blueprint",
)


def _sha(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_set_id(paths: tuple[Path, ...]) -> str:
    return _sha(
        [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in paths
        ]
    )


def _write_exclusive(path: Path, payload: object) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    args = parser.parse_args()

    source_commit = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT.parent,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if source_commit != args.expected_source_commit:
        raise ValueError("Round 5.13C source commit mismatch")
    if subprocess.run(
        ("git", "status", "--short"),
        cwd=ROOT.parent,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip():
        raise ValueError("Round 5.13C freezing requires a clean worktree")

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if any(output_root.iterdir()):
        raise ValueError("Round 5.13C output root must be empty")

    controller_id = _file_set_id(
        (ROOT / "agent/controller.py", ROOT / "dc3pa/integration/adapters.py")
    )
    evaluator_id = _file_set_id((ROOT / "agent/run_agent.py",))
    budget_id = _file_set_id((ROOT / "dc3pa/integration/stage6_config.py",))
    excluded_namespaces = tuple(
        _sha({"seed_namespace_domain": label})
        for label in (
            "acquisition",
            "historical_development",
            "engineering_smoke",
            "all_prior_holdout_sets",
            "final_evaluation_reserve",
        )
    )
    contracts = build_collection_contracts(
        source_commit=source_commit,
        method_contract_id=METHOD_CONTRACT_ID,
        historical_data_decision_id=HISTORICAL_DATA_DECISION_ID,
        dependency_schema_id=DEPENDENCY_SCHEMA_ID,
        paper_memory_v5_release_id=MEMORY_V5_RELEASE_ID,
        scene_exemplar_release_id=SCENE_RELEASE_ID,
        mineclip_policy_id=MINECLIP_POLICY_ID,
        parameter_provenance_policy_id=PARAMETER_PROVENANCE_ID,
        controller_contract_id=controller_id,
        evaluator_contract_id=evaluator_id,
        execution_budget_profile_id=budget_id,
        excluded_seed_namespace_ids=excluded_namespaces,
        dependency_support_threshold=2,
    )
    manifest_entries = []
    for name, contract in zip(CONTRACT_NAMES, contracts):
        path = output_root / f"{name}.json"
        payload = contract.to_dict()
        _write_exclusive(path, payload)
        manifest_entries.append(
            {
                "name": name,
                "id": payload[getattr(contract, "_id_field")],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    _write_exclusive(
        output_root / "manifest.json",
        {
            "source_commit": source_commit,
            "contract_count": len(contracts),
            "formal_seed_count": 0,
            "formal_assignments_generated": False,
            "contracts": manifest_entries,
        },
    )
    print(json.dumps({"output_root": str(output_root), "contracts": manifest_entries}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
