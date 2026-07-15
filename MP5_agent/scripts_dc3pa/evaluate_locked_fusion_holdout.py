#!/usr/bin/env python3
"""Single-use locked development holdout evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.reliability.activation_policy import load_activation_policy
from dc3pa.reliability.development_binding import activation_policy_id
from dc3pa.reliability.development_protocol import load_protocol
from dc3pa.reliability.fusion_artifact import load_fusion_artifact
from dc3pa.reliability.fusion_dataset import load_jsonl
from dc3pa.reliability.holdout_evaluation import (
    evaluate_holdout,
    save_holdout_report,
)
from dc3pa.reliability.holdout_lock import (
    claim_holdout_attempt,
    complete_holdout_attempt,
    fail_holdout_attempt,
    load_holdout_lock,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--holdout-dataset", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--activation-policy", required=True)
    parser.add_argument("--holdout-lock", required=True)
    parser.add_argument("--attempt-ledger", required=True)
    parser.add_argument("--output-report", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()

    protocol = load_protocol(args.protocol)
    policy = load_activation_policy(args.activation_policy)
    artifact = load_fusion_artifact(args.artifact)
    lock = load_holdout_lock(args.holdout_lock)
    protocol_id = protocol.protocol_id or protocol.compute_protocol_id()
    policy_id = policy.policy_id or policy.compute_policy_id()
    artifact_id = artifact.artifact_id or artifact.compute_artifact_id()

    if lock.development_protocol_id != protocol_id:
        raise ValueError("Lock and protocol IDs differ")
    if lock.activation_policy_id != policy_id:
        raise ValueError("Lock and activation policy IDs differ")
    if activation_policy_id(protocol) != policy_id:
        raise ValueError("Protocol and activation policy IDs differ")
    if lock.fusion_artifact_id != artifact_id:
        raise ValueError("Lock and fusion artifact IDs differ")
    if lock.source_commit != args.source_commit:
        raise ValueError("Lock source commit mismatch")
    lock.validate_files(
        holdout_dataset=args.holdout_dataset,
        fusion_artifact=args.artifact,
    )

    ledger = claim_holdout_attempt(
        args.attempt_ledger,
        lock=lock,
        output_report_path=args.output_report,
        source_commit=args.source_commit,
    )
    try:
        holdout = load_jsonl(Path(args.holdout_dataset))
        if any(item.split != "test" for item in holdout):
            raise ValueError("Locked paper holdout requires split='test'")
        report = evaluate_holdout(
            holdout,
            artifact=artifact,
            policy=policy,
            protocol_id=protocol_id,
            source_commit=args.source_commit,
        )
        save_holdout_report(
            args.output_report,
            report,
            refuse_overwrite=True,
        )
        complete_holdout_attempt(
            args.attempt_ledger,
            report_path=args.output_report,
        )
    except BaseException as exc:
        fail_holdout_attempt(args.attempt_ledger, error=exc)
        raise

    print(
        json.dumps(
            {
                "attempt_id": ledger.attempt_id,
                "report": report.to_dict(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
