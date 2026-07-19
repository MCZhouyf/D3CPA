#!/usr/bin/env python3
"""Write immutable Round 5.11 evidence-reconciliation sidecars."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round511_reconciliation import (
    Round511ReconciliationApproval,
    Round511ReconciliationPolicy,
    choose_salvage_path,
    reconcile_execution_budgets,
    reconcile_technical_failures,
)


def _write_json_exclusive(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _write_jsonl_exclusive(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def _artifact_id(payload: dict[str, Any]) -> str:
    value = dict(payload)
    value.pop("artifact_id", None)
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    policy = Round511ReconciliationPolicy().with_id()
    approval = None
    if args.approval is not None:
        approval = Round511ReconciliationApproval.from_mapping(
            json.loads(args.approval.read_text(encoding="utf-8"))
        )
    technical_rows, technical_summary = reconcile_technical_failures(
        args.campaign_root, policy=policy
    )
    budget_rows, budget_summary = reconcile_execution_budgets(
        args.campaign_root, repo_root=args.repo_root, policy=policy
    )
    decision = choose_salvage_path(
        technical_summary,
        budget_summary,
        retry_limit_violations=3,
        contamination_count=0,
        lineage_mismatch_count=0,
        remediation_approval=approval,
    )
    technical_summary = dict(technical_summary)
    technical_summary["artifact_id"] = _artifact_id(technical_summary)
    budget_summary = dict(budget_summary)
    budget_summary["artifact_id"] = _artifact_id(budget_summary)
    decision["technical_reconciliation_id"] = technical_summary["artifact_id"]
    decision["budget_reconciliation_id"] = budget_summary["artifact_id"]
    decision["artifact_id"] = _artifact_id(decision)

    _write_jsonl_exclusive(
        args.output_root / "technical_failure_reconciliation.jsonl", technical_rows
    )
    _write_json_exclusive(
        args.output_root / "technical_failure_reconciliation_summary.json",
        technical_summary,
    )
    _write_jsonl_exclusive(
        args.output_root / "execution_budget_reconciliation.jsonl", budget_rows
    )
    _write_json_exclusive(
        args.output_root / "execution_budget_reconciliation_summary.json",
        budget_summary,
    )
    _write_json_exclusive(args.output_root / "round511_salvage_decision.json", decision)
    print(json.dumps(decision, indent=2, sort_keys=True))
    return 0 if decision["mine_dojo_execution_permitted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
