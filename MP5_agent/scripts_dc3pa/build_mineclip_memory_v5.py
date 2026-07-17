#!/usr/bin/env python3
"""Rebuild frozen memory with official MineCLIP[attn]; no MineDojo execution."""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.experiments.mineclip_memory_v5 import MineCLIPV5RebuildContract
def load(p):
 v=json.loads(Path(p).read_text())
 if not isinstance(v,dict): raise ValueError("Expected JSON object")
 return v
def sha(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
 return h.hexdigest()
def verify_acquisition(root,manifest,expected_root):
 base=Path(root).resolve(); payload=load(manifest)
 if payload.get("root_sha256")!=expected_root:
  raise ValueError("Acquisition manifest root differs from the contract")
 expected=dict(payload.get("files",{})); actual={}
 for path in sorted(item for item in base.rglob("*") if item.is_file()):
  actual[path.relative_to(base).as_posix()]=sha(path)
 if actual!=expected:
  raise ValueError("Acquisition files differ from the bound manifest")
def main():
 p=argparse.ArgumentParser()
 for n in ("contract","acquisition-root","acquisition-manifest",
           "checkpoint","output-root","device"):
  p.add_argument("--"+n,required=True)
 p.add_argument("--existing-builder",default=str(ROOT/"scripts_dc3pa"/"build_frozen_memory.py"))
 a=p.parse_args()
 c=MineCLIPV5RebuildContract(**load(a.contract))
 if sha(a.acquisition_manifest)!=c.acquisition_manifest_sha256:
  raise ValueError("Acquisition manifest changed")
 verify_acquisition(a.acquisition_root,a.acquisition_manifest,c.acquisition_root_sha256)
 if sha(a.checkpoint)!=c.mineclip_checkpoint_sha256:
  raise ValueError("MineCLIP checkpoint changed")
 output=Path(a.output_root)
 if output.exists() and any(output.iterdir()): raise ValueError("Output root must be empty")
 encoder_config=json.dumps(
  {"checkpoint_path":str(Path(a.checkpoint).resolve()),"device":a.device},
  sort_keys=True,separators=(",",":")
 )
 snapshot_metadata=json.dumps({
  "mineclip_v5_rebuild_contract_id":c.contract_id,
  "active_taskset_release_id":c.active_taskset_release_id,
  "mineclip_policy_id":c.mineclip_policy_id,
  "mineclip_checkpoint_manifest_id":c.mineclip_checkpoint_manifest_id,
  "mineclip_checkpoint_sha256":c.mineclip_checkpoint_sha256,
  "mineclip_repository_commit":c.mineclip_repository_commit,
  "mineclip_variant":"attn",
  "scene_frame_strategy":"static_repeat_16",
  "image_encoder_identity":"dc3pa.memory.mineclip_scene_encoder:MineCLIPImageEncoder",
  "text_encoder_identity":"dc3pa.memory.mineclip_scene_encoder:MineCLIPTextEncoder",
  "acquisition_root_sha256":c.acquisition_root_sha256,
  "build_from_successful_records_only":True,
  "dependency_extraction_offline_only":True,
  "v4_engineering_release_id":c.v4_engineering_release_id,
  "v5_paper_candidate":True,
  "no_new_minedojo_episodes":True,
 },sort_keys=True,separators=(",",":"))
 cmd=[
  sys.executable,a.existing_builder,
  "--acquisition-root",str(Path(a.acquisition_root).resolve()),
  "--output-root",str(output.resolve()),
  "--source-commit",c.source_commit,
  "--min-dependency-support","2",
  "--image-encoder-factory","dc3pa.memory.mineclip_scene_encoder:build_mineclip_image_encoder",
  "--text-encoder-factory","dc3pa.memory.mineclip_scene_encoder:build_mineclip_text_encoder",
  "--encoder-config-json",encoder_config,
  "--snapshot-metadata-json",snapshot_metadata,
  "--require-encoders",
  "--reset-output",
 ]
 result=subprocess.run(cmd,check=False)
 if result.returncode: raise RuntimeError(f"Memory builder failed: {result.returncode}")
 manifest_path=output/"snapshot_manifest.json"
 stats_path=output/"build_stats.json"
 manifest=load(manifest_path);stats=load(stats_path)
 if manifest.get("metadata",{}).get("mineclip_v5_rebuild_contract_id")!=c.contract_id:
  raise ValueError("Sealed snapshot is missing the V5 rebuild contract")
 print(json.dumps({
  "snapshot_manifest":str(manifest_path),
  "build_stats":str(stats_path),
  "successful_episodes":stats.get("acquisition_episodes"),
  "scene_exemplars":stats.get("stored_scene_exemplars"),
  "dependency_edges":stats.get("retained_dependency_edges"),
  "action_key_coverage":stats.get("structured_action_key_coverage"),
 },indent=2,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
