#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.formal_acquisition_audit import (
    audit_formal_acquisition, load_ledgers
)
from dc3pa.experiments.formal_acquisition_execution import (
    FormalAcquisitionCampaign, TechnicalRetryPolicy
)

def load(path):
    value=json.loads(Path(path).read_text())
    if not isinstance(value,dict): raise ValueError("Expected JSON object")
    return value

def main():
    p=argparse.ArgumentParser()
    for n in ("campaign","schedule","authorization","blueprint","retry-policy",
              "ledger-root","acquisition-root","output"):
        p.add_argument("--"+n,required=True)
    a=p.parse_args()
    campaign_payload=load(a.campaign)
    campaign=FormalAcquisitionCampaign(**campaign_payload)
    retry_payload=load(a.retry_policy)
    retry_payload["allowed_categories"]=tuple(retry_payload["allowed_categories"])
    retry_payload["scientific_categories"]=tuple(retry_payload["scientific_categories"])
    retry=TechnicalRetryPolicy(**retry_payload)
    ledger_paths=sorted(Path(a.ledger_root).glob("*.json"))
    report=audit_formal_acquisition(
      campaign=campaign,
      schedule=load(a.schedule),
      authorization=load(a.authorization),
      blueprint=load(a.blueprint),
      retry_policy=retry,
      ledgers=load_ledgers(ledger_paths),
      acquisition_root=a.acquisition_root,
    )
    out=Path(a.output)
    if out.exists(): raise FileExistsError(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report.to_dict(),indent=2,sort_keys=True)+"\n")
    print(json.dumps(report.to_dict(),indent=2,sort_keys=True))
    return 0 if report.eligible else 2
if __name__=="__main__": raise SystemExit(main())
