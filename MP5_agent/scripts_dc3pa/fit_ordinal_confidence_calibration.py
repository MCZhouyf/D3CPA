#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.development_records import load_development_record
from dc3pa.experiments.ordinal_confidence_calibration import fit_confidence_calibration
def read(p):
 return [load_development_record(json.loads(x)) for x in Path(p).read_text().splitlines() if x.strip()]
def main():
 p=argparse.ArgumentParser()
 for n in ("release-name","source-commit","development-input-release-id","collection-audit-id","paper-memory-v5-release-id","active-taskset-release-id","train-jsonl","tune-jsonl","output"):
  p.add_argument("--"+n,required=True)
 p.add_argument("--alpha",type=float,default=1.0);a=p.parse_args()
 item=fit_confidence_calibration(release_name=a.release_name,source_commit=a.source_commit,development_input_release_id=a.development_input_release_id,collection_audit_id=a.collection_audit_id,paper_memory_v5_release_id=a.paper_memory_v5_release_id,active_taskset_release_id=a.active_taskset_release_id,train_records=read(a.train_jsonl),tune_records=read(a.tune_jsonl),alpha=a.alpha)
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(item.to_dict(),indent=2,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
