#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.mineclip_memory_v5 import (
 MineCLIPV5RebuildContract,compare_v4_v5
)
def load(p):
 v=json.loads(Path(p).read_text())
 if not isinstance(v,dict): raise ValueError("Expected JSON object")
 return v
def main():
 p=argparse.ArgumentParser()
 for n in ("contract","v4-release","v5-snapshot-release",
           "v5-build-stats","output"):
  p.add_argument("--"+n,required=True)
 a=p.parse_args()
 item=compare_v4_v5(
  contract=MineCLIPV5RebuildContract(**load(a.contract)),
  v4_release=load(a.v4_release),
  v5_release=load(a.v5_snapshot_release),
  v5_build_stats=load(a.v5_build_stats),
 )
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(item.to_dict(),indent=2,sort_keys=True))
 return 0 if item.eligible else 2
if __name__=="__main__": raise SystemExit(main())
