import hashlib
import json

import pytest

from dc3pa.experiments.mineclip_memory_v5 import MineCLIPV5RebuildContract
from scripts_dc3pa.build_mineclip_memory_v5 import verify_acquisition

def test_rebuild_contract_uses_same_acquisition_and_no_new_episodes():
 c=MineCLIPV5RebuildContract(
  contract_name="v5",source_commit="new",
  acquisition_source_commit="bb7469681509968b46e717c777ee782602087968",
  acquisition_audit_id="c65611a908a1e00d3ec1330f3f27e489b9c5848e2adc9a6b44685756cd2ea8df",
  acquisition_root_sha256="01ab1134830a4663d6cae9b747ecfe4c489fdd21bd51a278ede79face4981292",
  acquisition_manifest_sha256="manifest",
  v4_engineering_release_id="92bf4512d473addb4beec9a7909428215008ca624d6b802c055b00c15ecea5ce",
  v4_snapshot_root_sha256="53357cba689cfa6ff94f414a7f5e6c39ce1897c4cc5945f33fd6b8c05ca28e3f",
  active_taskset_release_id="taskset",active_taskset_catalog_sha256="catalog",
  mineclip_policy_id="policy",mineclip_checkpoint_manifest_id="ckpt",
  mineclip_checkpoint_sha256="sha",mineclip_checkpoint_md5="b5ece9198337cfd117a3bfbd921e56da",
  mineclip_repository_commit="e6c06a0245fac63dceb38bc9bd4fecd033dae735",
  successful_episode_count=40,min_dependency_support=2,
  expected_dependency_edges=27,expected_action_key_coverage=1.0,
 ).with_id()
 assert c.no_new_minedojo_episodes
 assert c.successful_episode_count==40

def test_acquisition_verification_rejects_file_drift(tmp_path):
 root=tmp_path/"acquisition";root.mkdir()
 episode=root/"episode.json";episode.write_text("{}")
 digest=hashlib.sha256(episode.read_bytes()).hexdigest()
 h=hashlib.sha256();h.update(b"episode.json\0");h.update(digest.encode());h.update(b"\0")
 manifest=tmp_path/"manifest.json"
 manifest.write_text(json.dumps({
  "root_sha256":h.hexdigest(),"files":{"episode.json":digest}
 }))
 verify_acquisition(root,manifest,h.hexdigest())
 episode.write_text('{"changed":true}')
 with pytest.raises(ValueError,match="Acquisition files differ"):
  verify_acquisition(root,manifest,h.hexdigest())
