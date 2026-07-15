#!/usr/bin/env python3
"""Reconstruct schema-v1 reference design at parent commit 15aa529.

This is not an official historical artifact. The output must be labeled
`reconstructed schema-v1 consistency check` and is used only to compare
protected semantics with schema-v2.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PARENT_COMMIT = "15aa529"


def run(command, *, cwd=None):
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--task-catalog", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    output = Path(args.output_dir).resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit("Output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)

    full_parent = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", PARENT_COMMIT],
        text=True,
    ).strip()
    with tempfile.TemporaryDirectory(prefix="dc3pa-v1-reconstruct-") as temp:
        worktree = Path(temp) / "worktree"
        run(
            [
                "git",
                "-C",
                str(repo),
                "worktree",
                "add",
                "--detach",
                str(worktree),
                full_parent,
            ]
        )
        try:
            script = (
                worktree
                / "MP5_agent/scripts_dc3pa/generate_gpt51_reference_design.py"
            )
            generated = Path(temp) / "generated"
            run(
                [
                    sys.executable,
                    str(script),
                    "--task-catalog",
                    str(Path(args.task_catalog).resolve()),
                    "--source-commit",
                    full_parent,
                    "--output-dir",
                    str(generated),
                ],
                cwd=worktree / "MP5_agent",
            )
            shutil.copytree(generated, output, dirs_exist_ok=True)
            design_path = output / "reference_design.json"
            target = output / "reconstructed_v1_design.json"
            design_path.rename(target)
            declaration = {
                "artifact_type": "reconstructed schema-v1 consistency check",
                "official_historical_artifact": False,
                "parent_commit": full_parent,
                "same_catalog_and_frozen_salts_required": True,
                "permitted_use": (
                    "protected semantic comparison with schema-v2 only"
                ),
            }
            (output / "reconstruction_declaration.json").write_text(
                json.dumps(declaration, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        finally:
            run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "worktree",
                    "remove",
                    "--force",
                    str(worktree),
                ]
            )
    print(
        json.dumps(
            {
                "parent_commit": full_parent,
                "output": str(output),
                "label": "reconstructed schema-v1 consistency check",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
