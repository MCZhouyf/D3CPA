#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.memory.mineclip_scene_encoder import MineCLIPEncoderPolicy
def main():
 p=argparse.ArgumentParser();p.add_argument("--output",required=True);a=p.parse_args()
 item=MineCLIPEncoderPolicy().with_id();out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(item.to_dict(),indent=2,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
