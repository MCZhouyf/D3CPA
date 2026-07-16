#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.formal_acquisition_schedule import build_formal_acquisition_schedule
def main():
 p=argparse.ArgumentParser()
 for n in ("design","schedule-name","source-commit","blueprint-id","policy-id","amendment-id","output"): p.add_argument("--"+n,required=True)
 a=p.parse_args(); design=json.loads(Path(a.design).read_text())
 item=build_formal_acquisition_schedule(design["acquisition_assignments"],schedule_name=a.schedule_name,source_commit=a.source_commit,blueprint_id=a.blueprint_id,bootstrap_policy_id=a.policy_id,bootstrap_amendment_id=a.amendment_id)
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps({"schedule_id":item.schedule_id,"episode_count":item.episode_count},indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
