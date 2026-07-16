#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.memory_snapshot_release import MemoryBuildContract

def load(path):
    value=json.loads(Path(path).read_text())
    if not isinstance(value,dict): raise ValueError("Expected JSON object")
    return value

def sha(path):
    h=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return h

def main():
    p=argparse.ArgumentParser()
    for n in ("contract-name","source-commit","campaign","acquisition-audit",
              "authorization","schedule","bootstrap-policy",
              "bootstrap-amendment","bootstrap-data-binding","blueprint-id",
              "image-encoder-identity","text-encoder-identity",
              "encoder-config","output"):
        p.add_argument("--"+n,required=True)
    p.add_argument("--min-dependency-support",type=int,default=2)
    a=p.parse_args()
    campaign=load(a.campaign); audit=load(a.acquisition_audit)
    authorization=load(a.authorization); schedule=load(a.schedule)
    policy=load(a.bootstrap_policy); amendment=load(a.bootstrap_amendment)
    binding=load(a.bootstrap_data_binding)
    if not audit.get("eligible",False):
        raise ValueError("Acquisition audit is ineligible")
    checks={
      "campaign":(audit.get("campaign_id"),campaign.get("campaign_id")),
      "authorization":(audit.get("formal_authorization_id"),authorization.get("authorization_id")),
      "schedule":(audit.get("schedule_id"),schedule.get("schedule_id")),
      "policy":(audit.get("bootstrap_policy_id"),policy.get("policy_id")),
      "amendment":(audit.get("bootstrap_amendment_id"),amendment.get("amendment_id")),
      "binding":(audit.get("bootstrap_data_binding_id"),binding.get("binding_id")),
      "Blueprint":(audit.get("blueprint_id"),a.blueprint_id),
      "source":(audit.get("source_commit"),a.source_commit),
    }
    bad=[name for name,(x,y) in checks.items() if x!=y]
    if bad: raise ValueError("Memory contract inputs mismatch: "+", ".join(bad))
    item=MemoryBuildContract(
      contract_name=a.contract_name,
      source_commit=a.source_commit,
      formal_acquisition_campaign_id=str(campaign["campaign_id"]),
      formal_acquisition_audit_id=str(audit["audit_id"]),
      formal_authorization_id=str(authorization["authorization_id"]),
      execution_tooling_binding_id=str(campaign["execution_tooling_binding_id"]),
      acquisition_schedule_id=str(schedule["schedule_id"]),
      bootstrap_policy_id=str(policy["policy_id"]),
      bootstrap_amendment_id=str(amendment["amendment_id"]),
      bootstrap_data_binding_id=str(binding["binding_id"]),
      blueprint_id=a.blueprint_id,
      acquisition_root_sha256=str(audit["acquisition_root_sha256"]),
      successful_acquisition_episode_count=int(audit["successful_episode_count"]),
      min_dependency_support=a.min_dependency_support,
      image_encoder_identity=a.image_encoder_identity,
      text_encoder_identity=a.text_encoder_identity,
      encoder_config_sha256=sha(a.encoder_config),
    ).with_id()
    out=Path(a.output)
    if out.exists(): raise FileExistsError(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
    print(json.dumps(item.to_dict(),indent=2,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
