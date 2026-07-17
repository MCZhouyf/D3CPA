#!/usr/bin/env python3
"""Audit task/difficulty/edge coverage of the paper-candidate memory."""
from __future__ import annotations
import argparse,json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.memory_coverage_audit import build_coverage_audit
def load(p):
 v=json.loads(Path(p).read_text())
 if not isinstance(v,dict): raise ValueError("Expected JSON object")
 return v
def load_jsonl_root(root):
 records=[]
 for p in sorted((Path(root)/"episodes").glob("*.json")):
  records.append(load(p))
 return records
def task_entries(payload):
 exclusion=payload.get("final_test_exclusion",payload)
 if not isinstance(exclusion,dict): raise ValueError("Final exclusion must be an object")
 tasks=exclusion.get("tasks",exclusion.get("covered_tasks",[]))
 if not isinstance(tasks,list): raise ValueError("Final exclusion tasks must be a list")
 return tasks
def covered_tasks(payload):
 return [
  task for task in task_entries(payload)
  if not task.get("goal_status") or task.get("goal_status")=="experience_covered"
 ]
def main():
 p=argparse.ArgumentParser()
 for n in ("paper-memory-release","active-taskset-release","acquisition-audit",
           "acquisition-root","database","covered-tasks",
           "final-exclusion","output"):
  p.add_argument("--"+n,required=True)
 a=p.parse_args()
 covered=covered_tasks(load(a.covered_tasks))
 exclusion=load(a.final_exclusion)
 heldout=[]; final_pairs=[]
 for task in task_entries(exclusion):
  if task.get("goal_status")=="final_heldout_terminal_goal": heldout.append(task["task"])
  for seed in task.get("test_seeds",[]): final_pairs.append((task["task"],str(seed)))
 conn=sqlite3.connect(f"file:{Path(a.database).resolve()}?mode=ro",uri=True)
 conn.row_factory=sqlite3.Row
 try:
  scenes=[dict(x) for x in conn.execute("SELECT * FROM scene_exemplars")]
  edges=[dict(x) for x in conn.execute("SELECT * FROM dependency_edges")]
 finally: conn.close()
 report=build_coverage_audit(
  paper_memory_release=load(a.paper_memory_release),
  active_taskset_release=load(a.active_taskset_release),
  acquisition_audit=load(a.acquisition_audit),
  acquisition_records=load_jsonl_root(a.acquisition_root),
  snapshot_rows={"scene_exemplars":scenes,"dependency_edges":edges},
  covered_tasks=covered,
  final_heldout_tasks=heldout,
  final_task_seed_pairs=final_pairs,
 )
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(report.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(report.to_dict(),indent=2,sort_keys=True))
 return 0 if report.eligible else 2
if __name__=="__main__": raise SystemExit(main())
