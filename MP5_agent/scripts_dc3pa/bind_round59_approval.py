#!/usr/bin/env python3
"""Create an immutable Round 5.9 approval binding outside the repository."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.design_migration import Round59ApprovalBinding,load_json
from dc3pa.experiments.model_epoch import save_immutable

def main():
    p=argparse.ArgumentParser()
    for name in ("blueprint-id","approval-record-id","approved-content-sha256",
                 "migration-report","reference-design-id","epoch-policy-version",
                 "schedule-policy-version","schedule-salt","output"):
        p.add_argument("--"+name,required=True)
    p.add_argument("--acknowledge-gpt51-mutable-alias-risk",action="store_true")
    a=p.parse_args(); report=load_json(a.migration_report)
    if not report.get("eligible"): raise SystemExit("Migration report is not eligible")
    item=Round59ApprovalBinding(blueprint_id=a.blueprint_id,
        approval_record_id=a.approval_record_id,
        approved_blueprint_content_sha256=a.approved_content_sha256,
        migration_report_id=str(report.get("report_id","")),
        reference_design_id=a.reference_design_id,
        mutable_alias_risk_acknowledged=a.acknowledge_gpt51_mutable_alias_risk,
        model_epoch_policy_version=a.epoch_policy_version,
        interleaved_schedule_policy_version=a.schedule_policy_version,
        interleaved_schedule_salt=a.schedule_salt).with_id()
    save_immutable(a.output,item.to_dict()); print(json.dumps(item.to_dict(),indent=2,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
