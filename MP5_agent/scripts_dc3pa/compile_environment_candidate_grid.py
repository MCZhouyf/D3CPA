#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.environment_grid_compiler import compile_grid_from_anchor
def main():
 p=argparse.ArgumentParser();p.add_argument("--anchor-config",required=True);p.add_argument("--anchor-config-id",required=True);p.add_argument("--output",required=True);a=p.parse_args()
 anchor=json.loads(Path(a.anchor_config).read_text())
 grid=compile_grid_from_anchor(anchor,anchor_config_id=a.anchor_config_id)
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(grid.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(grid.to_dict(),indent=2,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
