#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.formal_acquisition_execution import (
    EntryAttemptLedger, FormalAcquisitionCampaign
)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--campaign",required=True)
    p.add_argument("--schedule",required=True)
    p.add_argument("--output-root",required=True)
    a=p.parse_args()
    campaign_payload=json.loads(Path(a.campaign).read_text())
    campaign=FormalAcquisitionCampaign(**{
      k:v for k,v in campaign_payload.items()
      if k not in {"campaign_id"}
    },campaign_id=campaign_payload.get("campaign_id",""))
    schedule=json.loads(Path(a.schedule).read_text())
    if schedule["schedule_id"]!=campaign.schedule_id:
        raise ValueError("Campaign/schedule ID mismatch")
    entries=schedule.get("entries",[])
    if len(entries)!=100: raise ValueError("Schedule must contain 100 entries")
    out=Path(a.output_root)
    if out.exists(): raise FileExistsError(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix=f".{out.name}.",dir=out.parent))
    try:
        for entry in entries:
            item=EntryAttemptLedger(
              campaign_id=campaign.campaign_id,
              schedule_id=campaign.schedule_id,
              episode_index=int(entry["episode_index"]),
              group_id=str(entry["group_id"]),
              task=str(entry["task"]),
              seed=str(entry["seed"]),
              retry_policy_id=campaign.retry_policy_id,
            ).with_id()
            path=temp/f"{int(entry['episode_index']):03d}.json"
            path.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
        os.replace(temp,out)
    except Exception:
        shutil.rmtree(temp,ignore_errors=True)
        raise
    print(json.dumps({"ledger_count":len(entries),"output_root":str(out)},indent=2))
    return 0
if __name__=="__main__": raise SystemExit(main())
