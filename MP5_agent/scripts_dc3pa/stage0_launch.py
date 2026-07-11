#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MP5_ROOT = SCRIPT_DIR.parent
if str(MP5_ROOT) not in sys.path:
    sys.path.insert(0, str(MP5_ROOT))

from dc3pa.baseline.launcher import build_legacy_launch_spec, run_legacy
from dc3pa.baseline.metrics import parse_legacy_metrics
from dc3pa.config import load_config
from dc3pa.observability.manifest import create_run_manifest

_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_component(value: str, fallback: str) -> str:
    cleaned = _SAFE_COMPONENT.sub("-", value.strip()).strip("-._")
    return cleaned or fallback


def _default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _write_launch_record(run_dir: Path, spec, manifest) -> None:
    redacted = spec.redacted()
    (run_dir / "launch.json").write_text(
        json.dumps(
            {
                "command": redacted.command,
                "cwd": redacted.cwd,
                "selected_environment": manifest.selected_environment,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch manifested MP5 baseline runs")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--task")
    parser.add_argument("--model")
    parser.add_argument(
        "--seed",
        type=int,
        help="Run only this seed. Without it, run every seed in the config.",
    )
    parser.add_argument(
        "--run-id",
        help="Optional stable output group name. Defaults to a UTC timestamp.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    resolved_task = args.task or config.task_file
    resolved_model = args.model or config.model_name
    if not resolved_task:
        parser.error("A task file is required via --task or config.task_file")
    if not resolved_model:
        parser.error("A model name is required via --model or config.model_name")
    seeds = [args.seed] if args.seed is not None else list(config.seeds)
    run_id = _safe_component(args.run_id or _default_run_id(), "run")
    task_component = _safe_component(Path(resolved_task).stem, "task")
    repo_root = Path(args.repo_root).resolve()

    final_return_code = 0
    for seed in seeds:
        effective_config = replace(
            config,
            task_file=resolved_task,
            model_name=resolved_model,
            seeds=[seed],
        )
        effective_config.validate()
        spec = build_legacy_launch_spec(
            repo_root=repo_root,
            config=effective_config,
            seed=seed,
        )
        run_dir = (
            repo_root
            / effective_config.output_dir
            / task_component
            / run_id
            / f"seed_{seed}"
        )
        if run_dir.exists():
            parser.error(
                f"Run directory already exists: {run_dir}. Choose another --run-id; "
                "existing experiment outputs are never overwritten automatically."
            )
        run_dir.mkdir(parents=True, exist_ok=False)
        manifest = create_run_manifest(
            effective_config,
            repo_root,
            environment=spec.environment,
        )
        manifest.write(run_dir / "manifest.json")
        _write_launch_record(run_dir, spec, manifest)
        print(f"Manifest: {run_dir / 'manifest.json'}")
        print("Command:", " ".join(spec.redacted().command))
        if args.dry_run:
            continue

        legacy_log = repo_root / "MP5_agent" / "logs" / "agent.log"
        legacy_log_before = None
        if legacy_log.is_file():
            stat = legacy_log.stat()
            legacy_log_before = (stat.st_mtime_ns, stat.st_size)
        started = time.monotonic()
        completed = run_legacy(spec, tee_path=run_dir / "stdout.log")
        elapsed = time.monotonic() - started
        if legacy_log.is_file():
            stat = legacy_log.stat()
            legacy_log_after = (stat.st_mtime_ns, stat.st_size)
            if legacy_log_after != legacy_log_before:
                shutil.copy2(legacy_log, run_dir / "legacy_agent.log")
        metrics = parse_legacy_metrics(
            (completed.stdout or "").splitlines(),
            wall_clock_seconds=elapsed,
            return_code=completed.returncode,
        )
        metrics.write(run_dir / "metrics.json")
        print(f"Metrics: {run_dir / 'metrics.json'}")
        if completed.returncode != 0 and final_return_code == 0:
            final_return_code = int(completed.returncode)

    return final_return_code


if __name__ == "__main__":
    raise SystemExit(main())
