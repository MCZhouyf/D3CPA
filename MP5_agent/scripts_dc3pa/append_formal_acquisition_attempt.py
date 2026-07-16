#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.formal_acquisition_execution import (
    TechnicalRetryPolicy, load_attempt, load_ledger
)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",required=True)
    p.add_argument("--attempt",required=True)
    p.add_argument("--retry-policy",required=True)
    a=p.parse_args()
    ledger_path=Path(a.ledger)
    ledger=load_ledger(ledger_path)
    attempt=load_attempt(a.attempt)
    payload=json.loads(Path(a.retry_policy).read_text())
    payload["allowed_categories"]=tuple(payload["allowed_categories"])
    payload["scientific_categories"]=tuple(payload["scientific_categories"])
    policy=TechnicalRetryPolicy(**payload)
    if ledger.attempts and ledger.attempts[-1].receipt_id == attempt.receipt_id:
        print(json.dumps(ledger.to_dict(),indent=2,sort_keys=True))
        return 0
    updated=ledger.append(attempt,retry_policy=policy)
    temp=ledger_path.with_suffix(".json.tmp")
    with temp.open("w",encoding="utf-8") as handle:
        handle.write(json.dumps(updated.to_dict(),indent=2,sort_keys=True)+"\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp,ledger_path)
    print(json.dumps(updated.to_dict(),indent=2,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
