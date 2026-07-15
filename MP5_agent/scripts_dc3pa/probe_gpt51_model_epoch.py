#!/usr/bin/env python3
"""No-text epoch probe; Codex should expose a public metadata method."""
from __future__ import annotations
import argparse, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from dc3pa.providers import OpenAIResponsesChatAdapter, OpenAIResponsesModelProfile

PROTOCOL = "dc3pa-gpt51-model-epoch-probe-v1"
PROBE = 'Return exactly the JSON object {"probe":"ok"} and no other text.'
def sha(value): return hashlib.sha256(value.encode()).hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--purpose", default="planning")
    p.add_argument("--client-context-fingerprint", required=True)
    p.add_argument("--output-report", required=True)
    a = p.parse_args()
    profile = OpenAIResponsesModelProfile().with_id()
    adapter = OpenAIResponsesChatAdapter(profile=profile, purpose=a.purpose)
    response = adapter.invoke_with_metadata(PROBE)
    text = response.text
    if '"probe"' not in text or '"ok"' not in text:
        raise RuntimeError("Unexpected probe output")
    metadata = response.metadata
    usage = metadata.usage
    parsed = urlsplit(adapter.base_url)
    report = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "requested_model": profile.model,
        "returned_model": metadata.returned_model,
        "profile_id": profile.profile_id,
        "reasoning_effort": profile.reasoning_effort,
        "purpose": a.purpose,
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
    }
    out = Path(a.output_report)
    if out.exists(): raise FileExistsError(f"Refusing to overwrite {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print(json.dumps({
        "requested_model": report["requested_model"],
        "returned_model": report["returned_model"],
        "profile_id": report["profile_id"],
        "usage": {k: report[k] for k in (
            "input_tokens","output_tokens","reasoning_tokens","total_tokens")},
        "text_logged": False,
    }, indent=2, sort_keys=True))
    return 0
if __name__ == "__main__": raise SystemExit(main())
