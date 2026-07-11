#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MP5_ROOT = SCRIPT_DIR.parent
if str(MP5_ROOT) not in sys.path:
    sys.path.insert(0, str(MP5_ROOT))

from dc3pa.baseline.patcher import apply_guarded_legacy_patches


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply guarded Stage-0 patches")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    changes = apply_guarded_legacy_patches(args.repo_root, dry_run=args.dry_run)
    label = "Would apply" if args.dry_run else "Applied"
    if changes:
        print(f"{label} {len(changes)} guarded changes:")
        for change in changes:
            print(f"- {change}")
    else:
        print("No changes needed; patches are already present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
