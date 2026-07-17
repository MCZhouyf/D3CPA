from dc3pa.experiments.mineclip_memory_v5 import PaperMemoryV5Release

def test_paper_release_requires_mineclip_attn():
 r=PaperMemoryV5Release(
  release_name="paper-v5",source_commit="commit",rebuild_contract_id="contract",
  active_taskset_release_id="taskset",mineclip_policy_id="policy",
  mineclip_checkpoint_manifest_id="ckpt",frozen_memory_release_id="frozen",
  snapshot_manifest_sha256="manifest",snapshot_root_sha256="root",
  database_sha256="db",read_only_smoke_id="smoke",v4_v5_comparison_id="comparison",
  acquisition_audit_id="audit",acquisition_root_sha256="acq",
  successful_episode_count=40,scene_exemplar_count=120,
  dependency_edge_count=27,structured_action_key_coverage=1.0,
  min_dependency_support=2,encoder_name="MineCLIP",encoder_variant="attn",
  frame_strategy="static_repeat_16",embedding_dim=512,
  paper_candidate=True,eligible=True,
 ).with_id()
 assert r.release_id
