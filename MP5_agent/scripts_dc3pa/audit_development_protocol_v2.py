#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.development_protocol_v2 import DevelopmentAssignment,audit_development_protocol
def load(p):
 v=json.loads(Path(p).read_text())
 if not isinstance(v,dict): raise ValueError("Expected JSON object")
 return v
def main():
 p=argparse.ArgumentParser()
 for n in ("protocol-name","source-commit","active-taskset-release-id","final-exclusion-id","assignments","final-exclusion","holdout-sealed-manifest-hash","output"):
  p.add_argument("--"+n,required=True)
 a=p.parse_args();assignments=[DevelopmentAssignment(**x) for x in load(a.assignments)["assignments"]]
 exclusion=load(a.final_exclusion);heldout=[];pairs=[]
 for task in exclusion.get("tasks",[]):
  if task.get("goal_status")=="final_heldout_terminal_goal": heldout.append(task["task"])
  for seed in task.get("test_seeds",[]): pairs.append((task["task"],str(seed)))
 report=audit_development_protocol(protocol_name=a.protocol_name,source_commit=a.source_commit,active_taskset_release_id=a.active_taskset_release_id,final_exclusion_id=a.final_exclusion_id,assignments=assignments,final_heldout_tasks=heldout,final_task_seed_pairs=pairs,holdout_sealed_manifest_hash=a.holdout_sealed_manifest_hash)
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(report.to_dict(),indent=2,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
