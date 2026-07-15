#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from dc3pa.experiments.adjustment_protocol import AdjustmentRecord

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--proposal", required=True); p.add_argument("--output", required=True)
    a = p.parse_args()
    value = json.loads(Path(a.proposal).read_text())
    value["evidence_roles"] = tuple(value["evidence_roles"])
    value["evidence_artifact_sha256"] = tuple(value["evidence_artifact_sha256"])
    item = AdjustmentRecord(**value).with_id()
    out = Path(a.output)
    if out.exists(): raise FileExistsError(f"Refusing to overwrite {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(item.to_dict(), indent=2, sort_keys=True)+"\n")
    print(json.dumps(item.to_dict(), indent=2, sort_keys=True))
    return 0
if __name__ == "__main__": raise SystemExit(main())
