#!/usr/bin/env python3
"""Run the real MineDojo marker suite and emit a no-output-text receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-report", required=True)
    args = parser.parse_args()
    output = Path(args.output_report)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    command = [sys.executable, "-m", "pytest", "-q", "-m", "minedojo"]
    started = utc_now()
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    finished = utc_now()
    summary = re.search(r"(\d+) passed", result.stdout)
    source_commit = subprocess.check_output(
        ["git", "-C", str(ROOT.parent), "rev-parse", "HEAD"], text=True
    ).strip()
    report = {
        "command": command,
        "source_commit": source_commit,
        "test_count": int(summary.group(1)) if summary else 0,
        "exit_code": result.returncode,
        "started_at": started,
        "finished_at": finished,
        "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest(),
        "passed": result.returncode == 0,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
