#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.formal_bootstrap_authorization import FormalBootstrapReadinessEvidence,audit_formal_bootstrap_authorization
def load(p): return json.loads(Path(p).read_text())
def main():
 p=argparse.ArgumentParser()
 for n in ("source-commit","policy","amendment","blueprint-validation","approval-binding","taskset-release","migration-report","readiness","acquisition-schedule","output"): p.add_argument("--"+n,required=True)
 a=p.parse_args(); r=load(a.readiness)
 for n in ("run_receipt_ids","returned_model_identities","errors"): r[n]=tuple(r.get(n,()))
 readiness=FormalBootstrapReadinessEvidence(**r)
 item=audit_formal_bootstrap_authorization(source_commit=a.source_commit,policy=load(a.policy),amendment=load(a.amendment),blueprint_validation=load(a.blueprint_validation),approval_binding=load(a.approval_binding),taskset_release=load(a.taskset_release),migration_report=load(a.migration_report),readiness=readiness,acquisition_schedule=load(a.acquisition_schedule))
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(item.to_dict(),indent=2,sort_keys=True)); return 0 if item.formal_acquisition_permitted else 2
if __name__=="__main__": raise SystemExit(main())
