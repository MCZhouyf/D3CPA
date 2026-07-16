#!/usr/bin/env python3
"""Freeze an author-approved provider model-alias policy."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.provider_model_alias import (
    DECISION,
    ProviderModelAliasPolicy,
    sha256_file,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval-record", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    approval_path = Path(args.approval_record)
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    if approval.get("approved_by") != "ZYF":
        raise ValueError("Provider model-alias decision is not ZYF approved")
    if approval.get("decision") != DECISION:
        raise ValueError("Provider model-alias decision is not approved")
    if approval.get("requested_model") != "gpt-5.1":
        raise ValueError("Provider model-alias approval must request gpt-5.1")
    if not approval.get("preserve_returned_model_metadata", False):
        raise ValueError("Approval must preserve returned model metadata")

    policy = ProviderModelAliasPolicy(
        policy_name="dc3pa-zyf-provider-model-alias-v1",
        approved_by="ZYF",
        approved_at=str(approval["approved_at"]),
        approval_record_sha256=sha256_file(approval_path),
    ).with_id()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(policy.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(policy.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
