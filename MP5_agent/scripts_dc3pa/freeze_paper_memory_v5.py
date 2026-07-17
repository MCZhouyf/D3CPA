#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.mineclip_memory_v5 import (
 MineCLIPV5RebuildContract,MemoryV4V5Comparison,PaperMemoryV5Release
)
def load(p):
 v=json.loads(Path(p).read_text())
 if not isinstance(v,dict): raise ValueError("Expected JSON object")
 return v
def main():
 p=argparse.ArgumentParser()
 for n in ("release-name","source-commit","contract","active-taskset-release",
           "mineclip-policy","mineclip-checkpoint-manifest",
           "frozen-memory-release","snapshot-manifest","readonly-smoke",
           "comparison","output"):
  p.add_argument("--"+n,required=True)
 a=p.parse_args()
 import hashlib
 c=MineCLIPV5RebuildContract(**load(a.contract))
 taskset=load(a.active_taskset_release);policy=load(a.mineclip_policy)
 ckpt=load(a.mineclip_checkpoint_manifest);frozen=load(a.frozen_memory_release)
 smoke=load(a.readonly_smoke);cp=load(a.comparison)
 cp["errors"]=tuple(cp.get("errors",()))
 comparison=MemoryV4V5Comparison(**cp)
 if not comparison.eligible: raise ValueError("V4/V5 comparison is ineligible")
 if not frozen.get("eligible",False): raise ValueError("Frozen memory release is ineligible")
 if not smoke.get("eligible",False): raise ValueError("Read-only smoke is ineligible")
 snapshot_sha=hashlib.sha256(Path(a.snapshot_manifest).read_bytes()).hexdigest()
 if frozen.get("snapshot_manifest_sha256") not in (None,"",snapshot_sha):
  raise ValueError("Snapshot manifest SHA mismatch")
 item=PaperMemoryV5Release(
  release_name=a.release_name,
  source_commit=a.source_commit,
  rebuild_contract_id=c.contract_id,
  active_taskset_release_id=str(taskset["release_id"]),
  mineclip_policy_id=str(policy["policy_id"]),
  mineclip_checkpoint_manifest_id=str(ckpt["manifest_id"]),
  frozen_memory_release_id=str(frozen["release_id"]),
  snapshot_manifest_sha256=snapshot_sha,
  snapshot_root_sha256=str(frozen["snapshot_root_sha256"]),
  database_sha256=str(frozen["database_sha256"]),
  read_only_smoke_id=str(smoke["smoke_id"]),
  v4_v5_comparison_id=comparison.comparison_id,
  acquisition_audit_id=c.acquisition_audit_id,
  acquisition_root_sha256=c.acquisition_root_sha256,
  successful_episode_count=int(frozen["successful_episode_count"]),
  scene_exemplar_count=int(frozen["scene_exemplar_count"]),
  dependency_edge_count=int(frozen["dependency_edge_count"]),
  structured_action_key_coverage=float(frozen["structured_action_key_coverage"]),
  min_dependency_support=int(frozen["min_dependency_support"]),
  encoder_name="MineCLIP",
  encoder_variant="attn",
  frame_strategy="static_repeat_16",
  embedding_dim=512,
  paper_candidate=True,
  eligible=True,
 ).with_id()
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(item.to_dict(),indent=2,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
