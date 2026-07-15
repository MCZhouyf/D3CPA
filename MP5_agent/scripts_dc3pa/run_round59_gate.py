#!/usr/bin/env python3
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
TESTS = [
    "tests_dc3pa/test_round59_semantic_migration.py",
    "tests_dc3pa/test_round59_model_epoch.py",
    "tests_dc3pa/test_round59_interleaved_schedule.py",
    "tests_dc3pa/test_round59_adjustment_protocol.py",
    "tests_dc3pa/test_round59_readiness.py",
]
def main():
    p=argparse.ArgumentParser(); p.add_argument("--junit"); a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    tests=[x for x in TESTS if (root/x).exists()]
    if not tests: raise SystemExit("No Round 5.9 tests found")
    cmd=[sys.executable,"-m","pytest","-q",*tests]
    if a.junit:
        out=Path(a.junit); out.parent.mkdir(parents=True,exist_ok=True)
        cmd.append(f"--junitxml={out}")
    return subprocess.call(cmd,cwd=root)
if __name__=="__main__": raise SystemExit(main())
