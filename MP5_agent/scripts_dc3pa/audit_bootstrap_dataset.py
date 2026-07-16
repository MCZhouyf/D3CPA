#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.bootstrap_data_guard import audit_bootstrap_records
def main():
 p=argparse.ArgumentParser(); p.add_argument("--jsonl",required=True); p.add_argument("--policy-id",required=True); p.add_argument("--binding-id",required=True); p.add_argument("--output",required=True); a=p.parse_args()
 records=[json.loads(x) for x in Path(a.jsonl).read_text().splitlines() if x.strip()]
 item=audit_bootstrap_records(records,expected_policy_id=a.policy_id,expected_binding_id=a.binding_id)
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(item.to_dict(),indent=2,sort_keys=True)); return 0 if item.eligible else 2
if __name__=="__main__": raise SystemExit(main())
