#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.development_records import load_development_record,audit_development_collection
def load_jsonl(p):
 return [load_development_record(json.loads(line)) for line in Path(p).read_text().splitlines() if line.strip()]
def main():
 p=argparse.ArgumentParser()
 for n in ("jsonl","collection-id","development-input-release-id","development-protocol-id","paper-memory-v5-release-id","source-commit","output"):
  p.add_argument("--"+n,required=True)
 a=p.parse_args();records=load_jsonl(a.jsonl)
 report=audit_development_collection(records,collection_id=a.collection_id,development_input_release_id=a.development_input_release_id,development_protocol_id=a.development_protocol_id,paper_memory_v5_release_id=a.paper_memory_v5_release_id,source_commit=a.source_commit)
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(report.to_dict(),indent=2,sort_keys=True));return 0 if report.eligible else 2
if __name__=="__main__": raise SystemExit(main())
