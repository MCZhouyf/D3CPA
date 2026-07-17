import pytest

from dc3pa.memory.mineclip_scene_encoder import (
 MineCLIPEncoderPolicy,validate_official_direct_url
)

def test_mineclip_policy_is_official_attn_profile():
 p=MineCLIPEncoderPolicy().with_id()
 assert p.variant=="attn"
 assert p.repository_commit=="e6c06a0245fac63dceb38bc9bd4fecd033dae735"
 assert p.official_checkpoint_md5=="b5ece9198337cfd117a3bfbd921e56da"
 assert p.pool_type=="attn.d2.nh8.glusw"
 assert p.frame_strategy=="static_repeat_16"

def test_official_package_provenance_is_pinned_to_exact_commit():
 commit=validate_official_direct_url({
  "url":"https://github.com/MineDojo/MineCLIP.git",
  "vcs_info":{"vcs":"git","commit_id":
   "e6c06a0245fac63dceb38bc9bd4fecd033dae735"},
 })
 assert commit=="e6c06a0245fac63dceb38bc9bd4fecd033dae735"

def test_package_provenance_rejects_unpinned_commit():
 with pytest.raises(ValueError,match="pinned revision"):
  validate_official_direct_url({
   "url":"https://github.com/MineDojo/MineCLIP",
   "vcs_info":{"vcs":"git","commit_id":"wrong"},
  })
