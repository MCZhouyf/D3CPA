#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.taskset_canonicalization import (
 ActiveArtifactDescriptor,audit_active_taskset
)
def main():
 p=argparse.ArgumentParser()
 for n in ("source-commit","acquisition-source-commit","active-root",
           "catalog","descriptor-manifest","acquisition-audit","output"):
  p.add_argument("--"+n,required=True)
 a=p.parse_args()
 manifest=json.loads(Path(a.descriptor_manifest).read_text())
 descriptors=[ActiveArtifactDescriptor(**x) for x in manifest["artifacts"]]
 report=audit_active_taskset(
  source_commit=a.source_commit,
  acquisition_source_commit=a.acquisition_source_commit,
  active_root=a.active_root,
  catalog_path=a.catalog,
  descriptors=descriptors,
  acquisition_audit_path=a.acquisition_audit,
 )
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(report.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(report.to_dict(),indent=2,sort_keys=True))
 return 0 if report.eligible else 2
if __name__=="__main__": raise SystemExit(main())
