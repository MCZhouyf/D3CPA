#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.formal_acquisition_execution import (
    FormalAcquisitionCampaign, TechnicalRetryPolicy
)

def load(path):
    value=json.loads(Path(path).read_text())
    if not isinstance(value,dict): raise ValueError("Expected JSON object")
    return value

def sha(path):
    h=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return h

def main():
    p=argparse.ArgumentParser()
    for name in ("campaign-name","source-commit","blueprint","authorization",
                 "schedule","bootstrap-policy","bootstrap-amendment",
                 "execution-tooling-binding",
                 "bootstrap-data-binding","model-profile-id",
                 "prompt-hash-bundle-id","controller-identity-sha256",
                 "evaluator-identity-sha256","retry-policy","output"):
        p.add_argument("--"+name,required=True)
    a=p.parse_args()
    blueprint=load(a.blueprint); authorization=load(a.authorization)
    schedule=load(a.schedule); policy=load(a.bootstrap_policy)
    tooling=load(a.execution_tooling_binding)
    amendment=load(a.bootstrap_amendment); binding=load(a.bootstrap_data_binding)
    retry_payload=load(a.retry_policy)
    retry_payload["allowed_categories"]=tuple(retry_payload["allowed_categories"])
    retry_payload["scientific_categories"]=tuple(retry_payload["scientific_categories"])
    retry=TechnicalRetryPolicy(**retry_payload)
    checks={
      "authorization parent source":(authorization.get("source_commit"),tooling.get("parent_source_commit")),
      "schedule parent source":(schedule.get("source_commit"),tooling.get("parent_source_commit")),
      "blueprint parent source":(blueprint.get("source_commit"),tooling.get("parent_source_commit")),
      "authorization schedule":(authorization.get("acquisition_schedule_id"),schedule.get("schedule_id")),
      "tooling parent authorization":(tooling.get("parent_formal_authorization_id"),authorization.get("authorization_id")),
      "tooling new source":(tooling.get("new_source_commit"),a.source_commit),
      "authorization policy":(authorization.get("bootstrap_policy_id"),policy.get("policy_id")),
      "authorization amendment":(authorization.get("bootstrap_amendment_id"),amendment.get("amendment_id")),
      "binding policy":(binding.get("bootstrap_policy_id"),policy.get("policy_id")),
      "binding amendment":(binding.get("bootstrap_amendment_id"),amendment.get("amendment_id")),
      "binding Blueprint":(binding.get("blueprint_id"),blueprint.get("blueprint_id")),
      "binding source":(binding.get("source_commit"),a.source_commit),
      "binding scope":(binding.get("scope"),"formal_acquisition"),
      "binding method":(binding.get("method_id"),"single_chain_reactive_acquisition"),
      "binding tooling":(binding.get("execution_tooling_binding_id"),tooling.get("binding_id")),
      "binding parent authorization":(binding.get("parent_formal_authorization_id"),authorization.get("authorization_id")),
      "prompt identity":(a.prompt_hash_bundle_id,tooling.get("prompt_hash_bundle_id_after")),
      "Controller identity":(a.controller_identity_sha256,tooling.get("controller_identity_sha256_after")),
      "Evaluator identity":(a.evaluator_identity_sha256,tooling.get("evaluator_identity_sha256_after")),
      "schedule":(schedule.get("schedule_id"),tooling.get("acquisition_schedule_id")),
    }
    bad=[name for name,(x,y) in checks.items() if x!=y]
    if bad: raise ValueError("Campaign inputs mismatch: "+", ".join(bad))
    item=FormalAcquisitionCampaign(
      campaign_name=a.campaign_name,
      source_commit=a.source_commit,
      blueprint_id=str(blueprint["blueprint_id"]),
      formal_authorization_id=str(authorization["authorization_id"]),
      execution_tooling_binding_id=str(tooling["binding_id"]),
      schedule_id=str(schedule["schedule_id"]),
      bootstrap_policy_id=str(policy["policy_id"]),
      bootstrap_amendment_id=str(amendment["amendment_id"]),
      bootstrap_data_binding_id=str(binding["binding_id"]),
      model_profile_id=a.model_profile_id,
      prompt_hash_bundle_id=a.prompt_hash_bundle_id,
      controller_identity_sha256=a.controller_identity_sha256,
      evaluator_identity_sha256=a.evaluator_identity_sha256,
      retry_policy_id=retry.policy_id,
    ).with_id()
    out=Path(a.output)
    if out.exists(): raise FileExistsError(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
    print(json.dumps(item.to_dict(),indent=2,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
