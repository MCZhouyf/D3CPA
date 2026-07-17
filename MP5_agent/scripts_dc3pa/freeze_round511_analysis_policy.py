#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.development_analysis_policy import Round511AnalysisPolicy
from dc3pa.experiments.environment_parameter_selection import EnvironmentCandidate
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--policy-name",required=True)
 p.add_argument("--candidate-grid",required=True)
 p.add_argument("--output",required=True)
 a=p.parse_args()
 grid=json.loads(Path(a.candidate_grid).read_text())
 if grid.get("draft_only",False): raise ValueError("Candidate grid is still draft")
 candidates=tuple(EnvironmentCandidate(**x).with_id() for x in grid["candidates"])
 item=Round511AnalysisPolicy(
  policy_name=a.policy_name,
  confidence_levels=("very_low","low","medium","high","very_high"),
  confidence_alpha=1.0,
  confidence_method="symmetric_laplace_then_weighted_pav",
  environment_alpha=1.0,
  environment_candidates=candidates,
  environment_selection_objective="min_tune_brier_then_logloss_then_unknown_rate_then_id",
  environment_top_k=3,
  fusion_feature_order=("knowledge_coverage","knowledge_unknown","confidence_probability","environment_probability"),
  fusion_fitting_permitted=False,
  holdout_use_permitted=False,
  final_evaluation_use_permitted=False,
  outcome_adaptive_changes_permitted=False,
  policy_frozen_before_collection=True,
 ).with_id()
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(item.to_dict(),indent=2,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
