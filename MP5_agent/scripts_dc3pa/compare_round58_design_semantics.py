#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from dc3pa.experiments.design_migration import compare_designs, load_json

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--old-design", required=True)
    p.add_argument("--new-design", required=True)
    p.add_argument("--output-report", required=True)
    a = p.parse_args()
    report = compare_designs(load_json(a.old_design), load_json(a.new_design))
    out = Path(a.output_report)
    if out.exists(): raise FileExistsError(f"Refusing to overwrite {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True)+"\n")
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.eligible else 2
if __name__ == "__main__": raise SystemExit(main())
