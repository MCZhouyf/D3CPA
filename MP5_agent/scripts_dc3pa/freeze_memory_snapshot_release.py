#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.memory_snapshot_release import (
  MemoryBuildContract, ReadOnlySnapshotSmoke, audit_snapshot_and_build_release
)

def load(path):
    value=json.loads(Path(path).read_text())
    if not isinstance(value,dict): raise ValueError("Expected JSON object")
    return value

def main():
    p=argparse.ArgumentParser()
    for n in ("release-name","contract","acquisition-audit",
              "snapshot-manifest","build-stats","readonly-smoke","output"):
        p.add_argument("--"+n,required=True)
    a=p.parse_args()
    contract=MemoryBuildContract(**load(a.contract))
    smoke_payload=load(a.readonly_smoke)
    smoke_payload["errors"]=tuple(smoke_payload.get("errors",()))
    smoke=ReadOnlySnapshotSmoke(**smoke_payload)
    item=audit_snapshot_and_build_release(
      release_name=a.release_name,
      contract=contract,
      acquisition_audit=load(a.acquisition_audit),
      snapshot_manifest_path=a.snapshot_manifest,
      build_stats_path=a.build_stats,
      read_only_smoke=smoke,
    )
    out=Path(a.output)
    if out.exists(): raise FileExistsError(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
    print(json.dumps(item.to_dict(),indent=2,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
