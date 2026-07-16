#!/usr/bin/env python3
"""Invoke the existing offline builder and bind Round 5.10 provenance."""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.acquisition_binding import acquisition_root_manifest
from dc3pa.experiments.memory_snapshot_release import MemoryBuildContract
from dc3pa.memory.snapshot import create_snapshot_manifest

def load(path):
    value=json.loads(Path(path).read_text())
    if not isinstance(value,dict): raise ValueError("Expected JSON object")
    return value

def main():
    p=argparse.ArgumentParser()
    for n in ("contract","acquisition-audit","acquisition-root","output-root",
              "image-encoder-factory","text-encoder-factory",
              "encoder-config"):
        p.add_argument("--"+n,required=True)
    p.add_argument("--existing-builder",type=Path,
      default=ROOT/"scripts_dc3pa"/"build_frozen_memory.py")
    p.add_argument("--require-encoders",action="store_true",default=True)
    a=p.parse_args()
    contract_payload=load(a.contract)
    contract=MemoryBuildContract(**contract_payload)
    audit=load(a.acquisition_audit)
    if not audit.get("eligible",False): raise ValueError("Acquisition audit is ineligible")
    if audit.get("audit_id")!=contract.formal_acquisition_audit_id:
        raise ValueError("Audit/contract ID mismatch")
    root_manifest=acquisition_root_manifest(a.acquisition_root)
    if root_manifest["root_sha256"]!=contract.acquisition_root_sha256:
        raise ValueError("Acquisition root changed after audit")
    if a.image_encoder_factory!=contract.image_encoder_identity:
        raise ValueError("Image encoder factory/contract identity mismatch")
    if a.text_encoder_factory!=contract.text_encoder_identity:
        raise ValueError("Text encoder factory/contract identity mismatch")
    encoder_config_path=Path(a.encoder_config)
    if hashlib.sha256(encoder_config_path.read_bytes()).hexdigest()!=contract.encoder_config_sha256:
        raise ValueError("Encoder config/contract SHA-256 mismatch")
    encoder_config_json=encoder_config_path.read_text(encoding="utf-8")
    parsed_encoder_config=json.loads(encoder_config_json)
    if not isinstance(parsed_encoder_config,dict):
        raise ValueError("Encoder config must contain a JSON object")
    output=Path(a.output_root)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Memory output root must be absent or empty")
    command=[
      sys.executable,str(a.existing_builder),
      "--acquisition-root",str(Path(a.acquisition_root).resolve()),
      "--output-root",str(output.resolve()),
      "--source-commit",contract.source_commit,
      "--min-dependency-support",str(contract.min_dependency_support),
      "--reset-output",
      "--image-encoder-factory",a.image_encoder_factory,
      "--text-encoder-factory",a.text_encoder_factory,
      "--encoder-config-json",encoder_config_json,
      "--require-encoders",
    ]
    result=subprocess.run(command,check=False)
    if result.returncode!=0:
        raise RuntimeError(f"Existing memory builder failed with {result.returncode}")
    manifest_path=output/"snapshot_manifest.json"
    stats_path=output/"build_stats.json"
    manifest=load(manifest_path)
    stats=load(stats_path)
    metadata=dict(manifest.get("metadata",{}))
    metadata.update({
      "formal_acquisition_campaign_id":contract.formal_acquisition_campaign_id,
      "formal_acquisition_audit_id":contract.formal_acquisition_audit_id,
      "formal_authorization_id":contract.formal_authorization_id,
      "execution_tooling_binding_id":contract.execution_tooling_binding_id,
      "acquisition_schedule_id":contract.acquisition_schedule_id,
      "bootstrap_policy_id":contract.bootstrap_policy_id,
      "bootstrap_amendment_id":contract.bootstrap_amendment_id,
      "bootstrap_data_binding_id":contract.bootstrap_data_binding_id,
      "blueprint_id":contract.blueprint_id,
      "memory_build_contract_id":contract.contract_id,
      "image_encoder_identity":contract.image_encoder_identity,
      "text_encoder_identity":contract.text_encoder_identity,
      "encoder_config_sha256":contract.encoder_config_sha256,
      "dependency_extraction_offline_only":True,
      "build_from_successful_records_only":True,
    })
    acquisition_manifest_path=output/"acquisition_manifest.json"
    acquisition_manifest_path.write_text(
      json.dumps(root_manifest,indent=2,sort_keys=True)+"\n"
    )
    refreshed=create_snapshot_manifest(
      output/"memory.sqlite3",
      source_commit=contract.source_commit,
      metadata=metadata,
      snapshot_root=output,
      acquisition_manifest_path=acquisition_manifest_path,
      checkpoint_wal=True,
    )
    refreshed.to_json(manifest_path)
    result_payload={
      "output_root":str(output.resolve()),
      "snapshot_manifest":str(manifest_path),
      "build_stats":str(stats_path),
      "successful_episode_count":contract.successful_acquisition_episode_count,
      "retained_dependency_edges":stats.get("retained_dependency_edges"),
      "stored_scene_exemplars":stats.get("stored_scene_exemplars"),
      "structured_action_key_coverage":stats.get("structured_action_key_coverage"),
    }
    print(json.dumps(result_payload,indent=2,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
