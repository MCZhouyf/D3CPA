#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.development_records import load_development_record
from dc3pa.experiments.environment_parameter_selection import EnvironmentCandidate,select_environment_evidence
def read(p):
 return [load_development_record(json.loads(x)) for x in Path(p).read_text().splitlines() if x.strip()]
def main():
 p=argparse.ArgumentParser()
 for n in ("release-name","source-commit","development-input-release-id","collection-audit-id","paper-memory-v5-release-id","active-taskset-release-id","candidate-grid","train-jsonl","tune-jsonl","output"):
  p.add_argument("--"+n,required=True)
 p.add_argument("--alpha",type=float,default=1.0);a=p.parse_args()
 grid=json.loads(Path(a.candidate_grid).read_text());candidates=[EnvironmentCandidate(**x).with_id() for x in grid["candidates"]]
 item=select_environment_evidence(release_name=a.release_name,source_commit=a.source_commit,development_input_release_id=a.development_input_release_id,collection_audit_id=a.collection_audit_id,paper_memory_v5_release_id=a.paper_memory_v5_release_id,active_taskset_release_id=a.active_taskset_release_id,candidates=candidates,train_records=read(a.train_jsonl),tune_records=read(a.tune_jsonl),alpha=a.alpha)
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(item.to_dict(),indent=2,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
