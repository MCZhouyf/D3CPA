#!/usr/bin/env python3
"""Run the reproducible Round 1.1a engineering gate.

The hosted gate excludes tests explicitly marked ``minedojo``. It does not hide
ordinary failures and returns pytest's non-zero status unchanged.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
FOCUSED_TESTS = (
    "tests_dc3pa/test_round1_stage6_config.py",
    "tests_dc3pa/test_round1_execution_observer.py",
    "tests_dc3pa/test_round1_memory_lifecycle.py",
    "tests_dc3pa/test_round1_offline_builder.py",
    "tests_dc3pa/test_round11_local_subgoal.py",
    "tests_dc3pa/test_round11_telemetry_serialization.py",
    "tests_dc3pa/test_round11_calibration_store.py",
    "tests_dc3pa/test_round11_snapshot_assets.py",
    "tests_dc3pa/test_round11_persistence.py",
    "tests_dc3pa/test_round11_build_frozen_memory.py",
)
OPTIONAL_RUNTIME_MODULES = ("minedojo", "openai", "langchain", "requests")


def _module_status(names: Iterable[str]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for name in names:
        try:
            result[name] = importlib.util.find_spec(name) is not None
        except (ImportError, AttributeError, ValueError):
            result[name] = False
    return result


def diagnostics() -> dict[str, object]:
    missing_files = [name for name in FOCUSED_TESTS if not (ROOT / name).is_file()]
    payload: dict[str, object] = {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "cwd": str(Path.cwd()),
        "repo_root": str(ROOT),
        "optional_runtime_modules": _module_status(OPTIONAL_RUNTIME_MODULES),
        "focused_test_count": len(FOCUSED_TESTS),
        "missing_focused_tests": missing_files,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return payload


def _run(command: Sequence[str]) -> int:
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return int(completed.returncode)


def _compileall() -> int:
    return _run(
        [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "dc3pa",
            "scripts_dc3pa",
            "tests_dc3pa",
        ]
    )


def _pytest_args(*, junit: str | None, full: bool) -> list[str]:
    args = [sys.executable, "-m", "pytest", "-vv", "-x", "-m", "not minedojo"]
    if junit:
        junit_path = Path(junit)
        if not junit_path.is_absolute():
            junit_path = ROOT / junit_path
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        args.append(f"--junitxml={junit_path}")
    if full:
        args.append("tests_dc3pa")
    else:
        args.extend(FOCUSED_TESTS)
    return args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics-only", action="store_true")
    parser.add_argument("--unit", action="store_true", help="run focused hosted tests")
    parser.add_argument("--full", action="store_true", help="run all non-MineDojo tests")
    parser.add_argument("--junit", default="")
    parser.add_argument(
        "--skip-compile",
        action="store_true",
        help="do not run compileall before pytest",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = diagnostics()
    if payload["missing_focused_tests"]:
        print("Focused test files are missing; refusing to continue.", file=sys.stderr)
        return 2
    if args.diagnostics_only:
        return 0
    if not args.unit and not args.full:
        print("Choose --unit, --full, or --diagnostics-only.", file=sys.stderr)
        return 2
    if not args.skip_compile:
        status = _compileall()
        if status:
            return status
    return _run(_pytest_args(junit=args.junit or None, full=bool(args.full)))


if __name__ == "__main__":
    raise SystemExit(main())
