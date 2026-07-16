#!/usr/bin/env python3
"""No-text epoch probe; Codex should expose a public metadata method."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
from urllib.parse import urlsplit
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from dc3pa.providers import OpenAIResponsesChatAdapter, OpenAIResponsesModelProfile
from dc3pa.experiments.provider_model_alias import load_provider_model_alias_policy

PROTOCOL = "dc3pa-gpt51-model-epoch-probe-v1"
PROBE = 'Return exactly the JSON object {"probe":"ok"} and no other text.'
def sha(value): return hashlib.sha256(value.encode()).hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--purpose", default="planning")
    p.add_argument("--client-context-fingerprint", required=True)
    p.add_argument("--output-report", required=True)
    p.add_argument("--provider-model-alias-policy")
    p.add_argument("--provider-model-alias-approval")
    a = p.parse_args()
    profile = OpenAIResponsesModelProfile().with_id()
    alias_arguments = (a.provider_model_alias_policy, a.provider_model_alias_approval)
    if any(alias_arguments) and not all(alias_arguments):
        p.error(
            "model aliasing requires --provider-model-alias-policy and "
            "--provider-model-alias-approval"
        )
    alias_policy = None
    if all(alias_arguments):
        alias_policy = load_provider_model_alias_policy(
            a.provider_model_alias_policy,
            approval_record=a.provider_model_alias_approval,
        )
        alias_policy.assert_activation_allowed(
            scope="model_epoch_probe",
            requested_model=profile.model,
        )
    adapter = OpenAIResponsesChatAdapter(
        profile=profile,
        purpose=a.purpose,
        verify_returned_model=alias_policy is None,
    )
    response = adapter.invoke_with_metadata(PROBE)
    text = response.text
    if '"probe"' not in text or '"ok"' not in text:
        raise RuntimeError("Unexpected probe output")
    metadata = response.metadata
    usage = metadata.usage
    parsed = urlsplit(adapter.base_url)
    report = {
        "observed_at": metadata.request_started_at,
        "requested_model": metadata.requested_model,
        "returned_model": metadata.returned_model,
        "profile_id": metadata.profile_id,
        "reasoning_effort": metadata.reasoning_effort,
        "purpose": metadata.purpose,
        "request_succeeded": True,
        "request_text_logged": False,
        "response_text_logged": False,
        "endpoint_fingerprint": sha(f"{parsed.scheme}://{parsed.netloc}"),
        "client_context_fingerprint": a.client_context_fingerprint,
        "probe_protocol_id": PROTOCOL,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "total_tokens": usage.total_tokens,
        "response_id_sha256": metadata.response_id_sha256,
        "provider_model_alias_policy_id": (
            alias_policy.policy_id if alias_policy is not None else ""
        ),
    }
    out = Path(a.output_report)
    if out.exists(): raise FileExistsError(f"Refusing to overwrite {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print(json.dumps({
        "requested_model": report["requested_model"],
        "returned_model": report["returned_model"],
        "profile_id": report["profile_id"],
        "provider_model_alias_policy_id": report[
            "provider_model_alias_policy_id"
        ],
        "usage": {k: report[k] for k in (
            "input_tokens","output_tokens","reasoning_tokens","total_tokens")},
        "text_logged": False,
    }, indent=2, sort_keys=True))
    return 0
if __name__ == "__main__": raise SystemExit(main())
