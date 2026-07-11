#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MP5_ROOT = SCRIPT_DIR.parent
if str(MP5_ROOT) not in sys.path:
    sys.path.insert(0, str(MP5_ROOT))

from dc3pa.baseline.audit import audit_legacy_sources, write_audit_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit legacy MP5 sources for confounds")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--output", default="runs/stage0_audit.json")
    args = parser.parse_args()
    findings = audit_legacy_sources(args.repo_root)
    output = Path(args.output)
    if not output.is_absolute():
        output = Path(args.repo_root) / output
    write_audit_report(findings, output)
    print(f"Wrote {len(findings)} findings to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
