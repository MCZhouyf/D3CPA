#!/usr/bin/env python3
"""Capture a dirty Controller worktree patch outside Git before integration."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


BASE_SHA = "da85da1ad49ec1950ed505e3023fa7ff6b53ed2a"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args],
        text=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise SystemExit("Output directory must be empty")

    head = run(repo, "rev-parse", "HEAD").strip()
    if head != BASE_SHA:
        raise SystemExit(f"Expected HEAD {BASE_SHA}, found {head}")

    status = run(repo, "status", "--short")
    diff = run(repo, "diff", "--binary")
    staged = run(repo, "diff", "--cached", "--binary")
    if not status.strip():
        raise SystemExit("No dirty worktree changes found to preserve")

    status_path = output / "git_status_short.txt"
    patch_path = output / "unstaged.patch"
    staged_path = output / "staged.patch"
    status_path.write_text(status, encoding="utf-8")
    patch_path.write_text(diff, encoding="utf-8")
    staged_path.write_text(staged, encoding="utf-8")

    report = {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "repo_head": head,
        "status_sha256": sha256_file(status_path),
        "unstaged_patch_sha256": sha256_file(patch_path),
        "staged_patch_sha256": sha256_file(staged_path),
        "status_line_count": len([line for line in status.splitlines() if line]),
        "contains_uncommitted_changes": True,
    }
    (output / "dirty_worktree_manifest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
