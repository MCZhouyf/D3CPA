#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.memory.acquisition_scene_only import audit_scene_only_memory

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--database",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    item=audit_scene_only_memory(a.database)
    out=Path(a.output)
    if out.exists(): raise FileExistsError(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
    print(json.dumps(item.to_dict(),indent=2,sort_keys=True))
    return 0 if item.eligible else 2
if __name__=="__main__": raise SystemExit(main())
