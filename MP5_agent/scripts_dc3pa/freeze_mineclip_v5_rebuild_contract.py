#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.mineclip_memory_v5 import MineCLIPV5RebuildContract
def load(p):
 v=json.loads(Path(p).read_text())
 if not isinstance(v,dict): raise ValueError("Expected JSON object")
 return v
def main():
 p=argparse.ArgumentParser()
 for n in ("contract-name","source-commit","acquisition-audit",
           "acquisition-manifest","v4-release","active-taskset-release",
           "mineclip-policy","mineclip-checkpoint-manifest","output"):
  p.add_argument("--"+n,required=True)
 a=p.parse_args()
 audit=load(a.acquisition_audit);v4=load(a.v4_release)
 taskset=load(a.active_taskset_release);policy=load(a.mineclip_policy)
 ckpt=load(a.mineclip_checkpoint_manifest)
 if not audit.get("eligible",False): raise ValueError("Acquisition audit is ineligible")
 if not taskset.get("eligible",False): raise ValueError("Active taskset is ineligible")
 import hashlib
 acquisition_manifest_sha=hashlib.sha256(Path(a.acquisition_manifest).read_bytes()).hexdigest()
 item=MineCLIPV5RebuildContract(
  contract_name=a.contract_name,
  source_commit=a.source_commit,
  acquisition_source_commit=str(audit["source_commit"]),
  acquisition_audit_id=str(audit["audit_id"]),
  acquisition_root_sha256=str(audit["acquisition_root_sha256"]),
  acquisition_manifest_sha256=acquisition_manifest_sha,
  v4_engineering_release_id=str(v4["release_id"]),
  v4_snapshot_root_sha256=str(v4["snapshot_root_sha256"]),
  active_taskset_release_id=str(taskset["release_id"]),
  active_taskset_catalog_sha256=str(taskset["catalog_sha256"]),
  mineclip_policy_id=str(policy["policy_id"]),
  mineclip_checkpoint_manifest_id=str(ckpt["manifest_id"]),
  mineclip_checkpoint_sha256=str(ckpt["checkpoint_sha256"]),
  mineclip_checkpoint_md5=str(ckpt["checkpoint_md5"]),
  mineclip_repository_commit=str(policy["repository_commit"]),
  successful_episode_count=int(audit["successful_episode_count"]),
  min_dependency_support=2,
  expected_dependency_edges=27,
  expected_action_key_coverage=1.0,
 ).with_id()
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(item.to_dict(),indent=2,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
