#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.formal_bootstrap_authorization import audit_formal_bootstrap_readiness
def load(p): return json.loads(Path(p).read_text())
def main():
 p=argparse.ArgumentParser()
 for n in ("campaign-id","source-commit","blueprint-id","policy-id","amendment-id","model-epoch-id","output"): p.add_argument("--"+n,required=True)
 p.add_argument("--receipt",action="append",required=True); a=p.parse_args()
 item=audit_formal_bootstrap_readiness([load(x) for x in a.receipt],readiness_campaign_id=a.campaign_id,source_commit=a.source_commit,blueprint_id=a.blueprint_id,bootstrap_policy_id=a.policy_id,bootstrap_amendment_id=a.amendment_id,model_epoch_id=a.model_epoch_id)
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(item.to_dict(),indent=2,sort_keys=True)); return 0 if item.eligible else 2
if __name__=="__main__": raise SystemExit(main())
