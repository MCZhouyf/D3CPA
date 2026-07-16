#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from dc3pa.experiments.model_epoch import EpochPolicy, close_epoch, load_epoch, load_probe, open_epoch, save_immutable
from dc3pa.experiments.provider_model_alias import load_provider_model_alias_policy

def pair(value):
    if "=" not in value: raise argparse.ArgumentTypeError("Use NAME=SHA")
    key, item = value.split("=", 1)
    if not key.strip() or not item.strip(): raise argparse.ArgumentTypeError("Empty pair")
    return key.strip(), item.strip()

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="action", required=True)
    o = sub.add_parser("open")
    for name in ("epoch-name","blueprint-id","source-commit","model-profile-id",
                 "client-context-fingerprint","endpoint-fingerprint","schedule-id","output"):
        o.add_argument("--"+name, required=True)
    o.add_argument("--prompt-hash", action="append", type=pair, default=[])
    o.add_argument("--start-probe", action="append", required=True)
    o.add_argument("--provider-model-alias-policy")
    o.add_argument("--provider-model-alias-approval")
    c = sub.add_parser("close")
    c.add_argument("--open-epoch", required=True)
    c.add_argument("--end-probe", action="append", required=True)
    c.add_argument("--output", required=True)
    a = p.parse_args()
    if a.action == "open":
        alias_arguments = (
            a.provider_model_alias_policy,
            a.provider_model_alias_approval,
        )
        if any(alias_arguments) and not all(alias_arguments):
            p.error(
                "model aliasing requires --provider-model-alias-policy and "
                "--provider-model-alias-approval"
            )
        policy = EpochPolicy()
        if all(alias_arguments):
            alias_policy = load_provider_model_alias_policy(
                a.provider_model_alias_policy,
                approval_record=a.provider_model_alias_approval,
            )
            alias_policy.assert_activation_allowed(
                scope="model_epoch_probe",
                requested_model="gpt-5.1",
            )
            policy = EpochPolicy(
                require_returned_model_match=False,
                provider_model_alias_policy_id=alias_policy.policy_id,
            )
        item = open_epoch(
            epoch_name=a.epoch_name, blueprint_id=a.blueprint_id,
            source_commit=a.source_commit, prompt_hashes=dict(a.prompt_hash),
            model_profile_id=a.model_profile_id,
            client_context_fingerprint=a.client_context_fingerprint,
            endpoint_fingerprint=a.endpoint_fingerprint,
            schedule_id=a.schedule_id,
            start_probes=[load_probe(x) for x in a.start_probe],
            policy=policy,
        )
    else:
        item = close_epoch(load_epoch(a.open_epoch),
                           [load_probe(x) for x in a.end_probe])
    save_immutable(a.output, item.to_dict())
    print(json.dumps(item.to_dict(), indent=2, sort_keys=True))
    return 0 if item.status != "invalid" else 2
if __name__ == "__main__": raise SystemExit(main())
