#!/usr/bin/env python3
import argparse,subprocess,sys
from pathlib import Path
TESTS=["tests_dc3pa/test_round594_policy.py","tests_dc3pa/test_round594_event_receipt.py","tests_dc3pa/test_round594_amendment.py","tests_dc3pa/test_round594_dataset_guard.py","tests_dc3pa/test_round594_schedule.py","tests_dc3pa/test_round594_authorization.py","tests_dc3pa/test_round594_runtime_binding.py","tests_dc3pa/test_round594_approval.py"]
def main():
 p=argparse.ArgumentParser();p.add_argument("--junit");a=p.parse_args();root=Path(__file__).resolve().parents[1]
 cmd=[sys.executable,"-m","pytest","-q",*[x for x in TESTS if (root/x).exists()]]
 if a.junit: cmd.append(f"--junitxml={a.junit}")
 return subprocess.call(cmd,cwd=root)
if __name__=="__main__": raise SystemExit(main())
