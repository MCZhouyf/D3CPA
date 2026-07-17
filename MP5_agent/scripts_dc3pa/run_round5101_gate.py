#!/usr/bin/env python3
from __future__ import annotations
import argparse,subprocess,sys
from pathlib import Path
TESTS=[
 "tests_dc3pa/test_round5101_taskset.py",
 "tests_dc3pa/test_round5101_active_builder.py",
 "tests_dc3pa/test_round5101_mineclip_policy.py",
 "tests_dc3pa/test_round5101_static_scene.py",
 "tests_dc3pa/test_round5101_rebuild_contract.py",
 "tests_dc3pa/test_round5101_frozen_release.py",
 "tests_dc3pa/test_round5101_v4_v5_comparison.py",
 "tests_dc3pa/test_round5101_paper_release.py",
 "tests_dc3pa/test_round5101_coverage_audit.py",
]
def main():
 p=argparse.ArgumentParser();p.add_argument("--junit");a=p.parse_args()
 root=Path(__file__).resolve().parents[1]
 cmd=[sys.executable,"-m","pytest","-q",*[x for x in TESTS if (root/x).exists()]]
 if a.junit: cmd.append(f"--junitxml={a.junit}")
 return subprocess.call(cmd,cwd=root)
if __name__=="__main__": raise SystemExit(main())
