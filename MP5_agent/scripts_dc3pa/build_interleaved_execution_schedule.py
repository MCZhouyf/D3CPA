#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from dc3pa.experiments.execution_schedule import (
    DEFAULT_SALT,
    EvaluationUnit,
    MethodSpec,
    build_schedule,
)

def main():
    p = argparse.ArgumentParser()
    for name in ("methods","units","schedule-name","blueprint-id","source-commit",
                 "model-profile-id","output"):
        p.add_argument("--"+name, required=True)
    p.add_argument("--schedule-salt", default=DEFAULT_SALT)
    a = p.parse_args()
    methods = json.loads(Path(a.methods).read_text())
    units = json.loads(Path(a.units).read_text())
    result = build_schedule(
        schedule_name=a.schedule_name, blueprint_id=a.blueprint_id,
        source_commit=a.source_commit, model_profile_id=a.model_profile_id,
        methods=[MethodSpec(**x) for x in methods["methods"]],
        units=[EvaluationUnit(**x) for x in units["units"]],
        schedule_salt=a.schedule_salt,
    )
    out = Path(a.output)
    if out.exists(): raise FileExistsError(f"Refusing to overwrite {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True)+"\n")
    print(json.dumps({"schedule_id": result.schedule_id, "runs": len(result.runs)}, indent=2))
    return 0
if __name__ == "__main__": raise SystemExit(main())
