#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.development_records import load_development_record
from dc3pa.experiments.fusion_feature_freeze import (
 FusionFeatureExportRecord,freeze_fusion_feature_dataset
)
def load(p):
 v=json.loads(Path(p).read_text())
 if not isinstance(v,dict): raise ValueError("Expected JSON object")
 return v
def read(p):
 return [load_development_record(json.loads(x)) for x in Path(p).read_text().splitlines() if x.strip()]
def digest(v):
 return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def classify(record,candidate):
 similarities=tuple(record.environment_topk_similarities)
 maximum=max(similarities,default=0.0)
 if (not record.environment_topk_exemplar_ids or maximum<float(candidate["minimum_similarity"]) or record.environment_coverage<float(candidate["minimum_coverage"])):
  return "unknown"
 if record.environment_compatibility>=float(candidate["match_compatibility_threshold"]): return "matched"
 if record.environment_compatibility<=float(candidate["mismatch_compatibility_threshold"]): return "mismatch"
 return "unknown"
def main():
 p=argparse.ArgumentParser()
 for n in ("release-name","source-commit","development-input-release-id","collection-audit-id","paper-memory-v5-release-id","active-taskset-release-id","confidence-release","environment-release","train-decisions","tune-decisions","train-output","tune-output","release-output"):
  p.add_argument("--"+n,required=True)
 a=p.parse_args()
 confidence=load(a.confidence_release);environment=load(a.environment_release)
 conf_map={x["level"]:float(x["calibrated_probability"]) for x in confidence["levels"]}
 selected=environment["selected_result"];candidate=selected["candidate"];state_probs={k:float(v) for k,v in selected["state_probabilities"].items()}
 def convert(record):
  state=classify(record,candidate)
  rid=digest({"source":record.record_id,"confidence":confidence["release_id"],"environment":environment["release_id"]})
  return FusionFeatureExportRecord(
   feature_record_id=rid,source_decision_record_id=record.record_id,
   source_decision_record_hash=record.record_hash or record.compute_record_hash(),
   role=record.role,group_id=record.group_id,task=record.task,seed=record.seed,
   decision_index=record.decision_index,hard_feasible=record.knowledge_hard_feasible,
   knowledge_coverage=record.knowledge_coverage,knowledge_unknown=record.knowledge_unknown,
   confidence_probability=conf_map[record.confidence_level],
   environment_probability=state_probs[state],decision_correct=record.decision_correct,
   development_input_release_id=a.development_input_release_id,
   confidence_calibration_release_id=confidence["release_id"],
   environment_evidence_release_id=environment["release_id"],
   paper_memory_v5_release_id=a.paper_memory_v5_release_id,
  ).with_hash()
 train=[convert(x) for x in read(a.train_decisions)]
 tune=[convert(x) for x in read(a.tune_decisions)]
 release=freeze_fusion_feature_dataset(
  release_name=a.release_name,source_commit=a.source_commit,
  development_input_release_id=a.development_input_release_id,
  collection_audit_id=a.collection_audit_id,
  confidence_calibration_release_id=confidence["release_id"],
  environment_evidence_release_id=environment["release_id"],
  paper_memory_v5_release_id=a.paper_memory_v5_release_id,
  active_taskset_release_id=a.active_taskset_release_id,
  train_records=train,tune_records=tune,
  train_jsonl_path=a.train_output,tune_jsonl_path=a.tune_output,
 )
 out=Path(a.release_output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(release.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(release.to_dict(),indent=2,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
