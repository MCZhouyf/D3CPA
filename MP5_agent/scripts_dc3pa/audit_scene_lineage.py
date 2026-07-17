#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.scene_lineage_audit import (
 SuccessfulTaskEvidence,SceneCandidateLineage,audit_scene_lineage
)
def main():
 p=argparse.ArgumentParser()
 for n in ("input","paper-memory-release-id","acquisition-audit-id","output"):
  p.add_argument("--"+n,required=True)
 a=p.parse_args();payload=json.loads(Path(a.input).read_text())
 successful=[SuccessfulTaskEvidence(task=x["task"],successful_episode_ids=tuple(x["successful_episode_ids"])) for x in payload["successful_tasks"]]
 lineage=[SceneCandidateLineage(**x) for x in payload["candidate_lineage"]]
 report=audit_scene_lineage(paper_memory_release_id=a.paper_memory_release_id,acquisition_audit_id=a.acquisition_audit_id,successful_tasks=successful,candidate_lineage=lineage)
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(report.to_dict(),indent=2,sort_keys=True));return 0 if report.eligible else 2
if __name__=="__main__": raise SystemExit(main())
