#!/usr/bin/env python3
"""Probe the exact GPT-5.1 snapshot without exposing prompt or response text."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.providers import (
    OpenAIResponsesChatAdapter,
    OpenAIResponsesModelProfile,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--purpose", default="planning")
    parser.add_argument("--output-report", required=True)
    args = parser.parse_args()

    observed = []
    profile = OpenAIResponsesModelProfile().with_id()
    adapter = OpenAIResponsesChatAdapter(
        profile=profile,
        purpose=args.purpose,
        usage_observer=observed.append,
    )
    result = adapter.predict(
        "Return exactly the JSON object {\"probe\":\"ok\"} and no other text."
    )
    if "\"probe\"" not in result or "\"ok\"" not in result:
        raise RuntimeError("GPT-5.1 probe returned unexpected output")
    usage = observed[-1] if observed else None
    report = {
        "profile_id": profile.profile_id,
        "model": profile.model,
        "reasoning_effort": profile.reasoning_effort,
        "purpose": args.purpose,
        "request_succeeded": True,
        "response_text_logged": False,
        "usage": None if usage is None else usage.__dict__,
    }
    output = Path(args.output_report)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite probe report: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
