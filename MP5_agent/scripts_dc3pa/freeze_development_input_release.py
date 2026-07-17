#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.development_input_release import build_development_input_release
def load(p):
 v=json.loads(Path(p).read_text())
 if not isinstance(v,dict): raise ValueError("Expected JSON object")
 return v
def main():
 p=argparse.ArgumentParser()
 for n in ("release-name","source-commit","active-taskset","mineclip-policy","checkpoint-manifest","v5-contract","paper-memory","readonly-smoke","coverage-audit","scene-lineage-audit","bootstrap-policy","bootstrap-amendment","prompt-hash-bundle-id","controller-identity-sha256","evaluator-identity-sha256","development-protocol-id","development-tooling-binding-id","analysis-policy-id","final-exclusion-id","output"):
  p.add_argument("--"+n,required=True)
 a=p.parse_args()
 item=build_development_input_release(
  release_name=a.release_name,source_commit=a.source_commit,
  active_taskset=load(a.active_taskset),mineclip_policy=load(a.mineclip_policy),
  checkpoint_manifest=load(a.checkpoint_manifest),v5_contract=load(a.v5_contract),
  paper_memory=load(a.paper_memory),readonly_smoke=load(a.readonly_smoke),
  coverage_audit=load(a.coverage_audit),scene_lineage_audit=load(a.scene_lineage_audit),
  bootstrap_policy=load(a.bootstrap_policy),bootstrap_amendment=load(a.bootstrap_amendment),
  prompt_hash_bundle_id=a.prompt_hash_bundle_id,
  controller_identity_sha256=a.controller_identity_sha256,
  evaluator_identity_sha256=a.evaluator_identity_sha256,
  development_protocol_id=a.development_protocol_id,
  development_tooling_binding_id=a.development_tooling_binding_id,
  analysis_policy_id=a.analysis_policy_id,
  final_exclusion_id=a.final_exclusion_id,
 )
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(item.to_dict(),indent=2,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
