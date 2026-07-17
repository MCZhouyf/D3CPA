#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.taskset_canonicalization import (
 ActivePressurePlateTasksetRelease,PressurePlateCanonicalizationReport
)
def load(p):
 v=json.loads(Path(p).read_text())
 if not isinstance(v,dict): raise ValueError("Expected JSON object")
 return v
def main():
 p=argparse.ArgumentParser()
 for n in ("release-name","canonicalization-report","acquisition-audit","output"):
  p.add_argument("--"+n,required=True)
 a=p.parse_args()
 rp=load(a.canonicalization_report)
 for n in ("scans","errors","warnings"): rp[n]=tuple(rp.get(n,()))
 from dc3pa.experiments.taskset_canonicalization import TaskReferenceScan
 rp["scans"]=tuple(TaskReferenceScan(**x) for x in rp["scans"])
 report=PressurePlateCanonicalizationReport(**rp)
 audit=load(a.acquisition_audit)
 item=ActivePressurePlateTasksetRelease(
  release_name=a.release_name,
  source_commit=report.source_commit,
  acquisition_source_commit=report.acquisition_source_commit,
  canonicalization_report_id=report.report_id,
  active_root_sha256=report.active_root_sha256,
  catalog_sha256=report.catalog_sha256,
  acquisition_audit_id=str(audit["audit_id"]),
  acquisition_root_sha256=str(audit["acquisition_root_sha256"]),
  pressure_plate_task_name="craft wooden pressure plate",
  old_task_name="mine sand",
  pressure_plate_acquisition_successes=report.pressure_plate_acquisition_successes,
  active_task_count=report.task_count,
  active_difficulty_counts=report.difficulty_counts,
  historical_artifacts_mutated=False,
  active_artifacts_fully_replaced=True,
  eligible=report.eligible,
 ).with_id()
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(item.to_dict(),indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
