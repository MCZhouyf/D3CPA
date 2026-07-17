#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from dc3pa.memory.mineclip_scene_encoder import (
 MineCLIPCheckpointManifest,MineCLIPEncoderPolicy,load_official_model
)
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--checkpoint",required=True);p.add_argument("--output",required=True)
 p.add_argument("--device");a=p.parse_args()
 policy=MineCLIPEncoderPolicy().with_id()
 encoder,meta=load_official_model(checkpoint_path=a.checkpoint,policy=policy,device=a.device)
 image=np.zeros((160,256,3),dtype=np.uint8)
 first=encoder.encode_image(image);second=encoder.encode_image(image)
 text=encoder.encode_text("craft a wooden pressure plate")
 deterministic=bool(np.array_equal(first,second) or np.allclose(first,second,rtol=0,atol=1e-6))
 config_sha=hashlib.sha256(
  json.dumps(policy.model_kwargs(),sort_keys=True,separators=(",",":")).encode()
 ).hexdigest()
 item=MineCLIPCheckpointManifest(
  policy_id=policy.policy_id,
  checkpoint_filename=Path(a.checkpoint).name,
  checkpoint_sha256=meta["checkpoint_sha256"],
  checkpoint_md5=meta["checkpoint_md5"],
  checkpoint_size_bytes=meta["checkpoint_size_bytes"],
  config_sha256=config_sha,
  torch_version=meta["torch_version"],
  mineclip_package_location_fingerprint=meta["mineclip_package_location_fingerprint"],
  mineclip_repository=meta["mineclip_repository"],
  mineclip_repository_commit=meta["mineclip_repository_commit"],
  device_type=meta["device_type"],
  dtype="float32-output,uint8-video-input",
  checkpoint_loaded_strictly=True,
  inference_probe_passed=bool(np.isfinite(first).all() and np.isfinite(text).all()),
  image_embedding_dim=int(first.shape[0]),
  text_embedding_dim=int(text.shape[0]),
  image_embedding_shape=tuple(int(x) for x in first.shape),
  text_embedding_shape=tuple(int(x) for x in text.shape),
  image_embedding_l2_norm=float(np.linalg.norm(first)),
  text_embedding_l2_norm=float(np.linalg.norm(text)),
  deterministic_repeat_max_abs_diff=float(np.max(np.abs(first-second))),
  deterministic_repeat_probe_passed=deterministic,
 ).with_id()
 out=Path(a.output)
 if out.exists(): raise FileExistsError(out)
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(item.to_dict(),indent=2,sort_keys=True)+"\n")
 print(json.dumps(item.to_dict(),indent=2,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
