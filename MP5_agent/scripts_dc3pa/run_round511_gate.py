#!/usr/bin/env python3
from __future__ import annotations
import argparse,subprocess,sys
from pathlib import Path
TESTS=[
 "tests_dc3pa/test_round511_scene_lineage.py",
 "tests_dc3pa/test_round511_scene_lineage_builder.py",
 "tests_dc3pa/test_round511_analysis_policy.py",
 "tests_dc3pa/test_round511_tooling_binding.py",
 "tests_dc3pa/test_round511_development_protocol.py",
 "tests_dc3pa/test_round511_development_records.py",
 "tests_dc3pa/test_round511_development_shadow.py",
 "tests_dc3pa/test_round511_campaign_runner.py",
 "tests_dc3pa/test_round511_confidence.py",
 "tests_dc3pa/test_round511_environment.py",
 "tests_dc3pa/test_round511_environment_grid.py",
 "tests_dc3pa/test_round511_fusion_freeze.py",
]
def main():
 p=argparse.ArgumentParser();p.add_argument("--junit");a=p.parse_args()
 root=Path(__file__).resolve().parents[1]
 selected=[x for x in TESTS if (root/x).exists()]
 cmd=[sys.executable,"-m","pytest","-q",*selected]
 if a.junit: cmd.append(f"--junitxml={a.junit}")
 return subprocess.call(cmd,cwd=root)
if __name__=="__main__": raise SystemExit(main())
