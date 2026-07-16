#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.bootstrap_metrics import aggregate_bootstrap_receipts
def main():
 p=argparse.ArgumentParser()
 for n in ("policy-id","amendment-id","source-commit","blueprint-id","output"): p.add_argument("--"+n,required=True)
 p.add_argument("--receipt",action="append",required=True); a=p.parse_args()
 receipts=[json.loads(Path(x).read_text()) for x in a.receipt]
 item=aggregate_bootstrap_receipts(receipts,bootstrap_policy_id=a.policy_id,bootstrap_amendment_id=a.amendment_id,source_commit=a.source_commit,blueprint_id=a.blueprint_id)
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(item.to_dict(),indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
