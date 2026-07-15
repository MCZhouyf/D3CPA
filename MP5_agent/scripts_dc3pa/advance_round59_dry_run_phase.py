#!/usr/bin/env python3
"""Advance dry_run_completed only with eligible Round 5.9 evidence."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.model_epoch import load_epoch
from dc3pa.experiments.phase_state import load_state,save_state_atomic

def main():
    p=argparse.ArgumentParser()
    for name in ("phase-state","readiness-report","closed-model-epoch",
                 "source-commit","output-state"):
        p.add_argument("--"+name,required=True)
    a=p.parse_args(); readiness=json.loads(Path(a.readiness_report).read_text())
    epoch=load_epoch(a.closed_model_epoch); state=load_state(a.phase_state)
    if not readiness.get("eligible"): raise SystemExit("Readiness is not eligible")
    if epoch.status!="closed" or epoch.invariant_errors():
        raise SystemExit("Model epoch is not validly closed")
    if readiness.get("model_epoch_id")!=epoch.epoch_id:
        raise SystemExit("Readiness/model epoch mismatch")
    if readiness.get("blueprint_id")!=state.experiment_id:
        raise SystemExit("Readiness/phase-state Blueprint mismatch")
    advanced=state.advance(phase="dry_run_completed",source_commit=a.source_commit,
        artifact_ids={"round59_readiness_id":readiness["readiness_id"],
                      "closed_model_epoch_id":epoch.epoch_id})
    save_state_atomic(a.output_state,advanced)
    print(json.dumps(advanced.to_dict(),indent=2,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
