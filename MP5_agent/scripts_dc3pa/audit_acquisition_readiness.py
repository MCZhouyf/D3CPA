#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from dc3pa.experiments.model_epoch import load_epoch
from dc3pa.experiments.readiness import audit_readiness, load_receipt

def load(path): return json.loads(Path(path).read_text())
def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""): h.update(chunk)
    return h.hexdigest()

def main():
    p = argparse.ArgumentParser()
    for name in ("blueprint-id","source-commit","migration-report",
                 "approval-binding",
                 "blueprint-validation","closed-model-epoch",
                 "dry-run-audit","minedojo-marker-report","output-report"):
        p.add_argument("--"+name, required=True)
    p.add_argument("--smoke-receipt", action="append", required=True)
    a = p.parse_args()
    marker = load(a.minedojo_marker_report)
    result = audit_readiness(
        blueprint_id=a.blueprint_id,
        source_commit=a.source_commit,
        migration_report=load(a.migration_report),
        approval_binding=load(a.approval_binding),
        blueprint_validation=load(a.blueprint_validation),
        model_epoch=load_epoch(a.closed_model_epoch),
        dry_run_audit=load(a.dry_run_audit),
        dry_run_audit_sha256=sha_file(a.dry_run_audit),
        smoke_receipts=[load_receipt(x) for x in a.smoke_receipt],
        minedojo_marker_passed=bool(marker.get("passed", False)),
    )
    out = Path(a.output_report)
    if out.exists(): raise FileExistsError(f"Refusing to overwrite {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True)+"\n")
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.eligible else 2
if __name__ == "__main__": raise SystemExit(main())
