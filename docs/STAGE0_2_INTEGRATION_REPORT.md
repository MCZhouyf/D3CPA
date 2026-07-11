# Stage 0-2 Integration Report

## Scope

Integrated `D3CPA_stage0_2_overlay_v0.3.0.zip` into `MCZhouyf/D3CPA` at base commit `0935ecf30d1c0fc246fc5ce9b421a6cfa3c63179`.

Integration commit reviewed for this report: `2cfe024` (`Integrate DC3PA stages 0-2 overlay`).

The manuscript PDF was not available in the repository or overlay. I therefore used `docs/PAPER_ALIGNMENT_STAGE0_2.md` as the available paper-alignment contract and do not claim details beyond that document.

Stage 3 has not been implemented. This integration does not add the Hybrid Probability Model, Dual-Chain Evaluation behavior, Evaluation Chain corrections, reliability fusion, adaptive triggers, or paper-level end-to-end reproduction claims.

## Review Passes

Pass 1 repository reconnaissance:

- Read `docs/PAPER_ALIGNMENT_STAGE0_2.md` because no PDF/manuscript file was available.
- Inspected `MP5_agent/agent/run_agent.py`, `planner.py`, `controller.py`, `work_memory.py`, prompt files, task files, and run scripts.
- Compared current core sources against `dc3pa/baseline/patcher.py` guarded anchors.
- Found source drift in `run_agent.py`: current MineDojo simulator seed appears inline as `target_quantities=100, seed=3,`, while the overlay patcher expected a standalone `seed=3,` line.

Pass 2 adversarial design review:

- Import risk from `MP5_agent/agent` launch cwd is handled by adding `MP5_agent/agent/dc3pa_feature_flags.py`; verified directly from that cwd.
- World seed, MineDojo simulator seed, Python `random`, NumPy and `PYTHONHASHSEED` are exposed through the Stage 0 launcher and patched runner.
- Task-specific inventory mutation and deep-mining helper branches remain present in legacy code, but the known deep-mining entry point is gated by `DC3PA_LEGACY_TASK_HACKS` for research-clean mode. The original empty initial inventory line remains legacy behavior and is reported by audit.
- Stage 1 plan round-trip preserves the Controller-compatible legacy shape: `workflow`, string `times`, `actions`, and `args`.
- Failed episodes cannot add dependency edges or scene exemplars; this is enforced by store checks and tested.
- Stage 2 memory writes use one SQLite transaction and remove newly copied image files on failure.
- Vector dimension mismatches return no similarity instead of forcing invalid comparisons; non-finite vectors are rejected.

## Files Changed

Major groups:

- Legacy gates and reproducibility: `MP5_agent/agent/run_agent.py`, `planner.py`, `controller.py`, `dc3pa_feature_flags.py`.
- Stage 0-2 package: `MP5_agent/dc3pa/**`.
- Scripts: `MP5_agent/scripts_dc3pa/**`.
- Tests: `MP5_agent/tests_dc3pa/**`.
- Docs and audit: `docs/**`, `runs/stage0_audit.json`.
- Test tracking adjustment: `MP5_agent/.gitignore` now explicitly allows `tests_dc3pa/`.

Repository-specific adjustment:

- `MP5_agent/dc3pa/baseline/patcher.py` now supports two exact simulator-seed anchors: the overlay fixture form `seed=3,` and this repository's inline form `target_quantities=100, seed=3,`. This is still guarded replacement: it requires exactly one known anchor and does not use fuzzy matching.

## Commands And Results

- `sha256sum -c D3CPA_stage0_2_overlay_v0.3.0.zip.sha256` from `/root/autodl-tmp`: passed.
- `python <overlay>/apply_overlay.py --repo-root .`: copied 55 overlay files.
- `python MP5_agent/scripts_dc3pa/apply_legacy_patches.py --repo-root . --dry-run`: initially failed on the inline MineDojo seed anchor, then passed after the exact-anchor repository adjustment.
- `python MP5_agent/scripts_dc3pa/apply_legacy_patches.py --repo-root .`: passed and reported no changes needed after manual narrow integration.
- `python MP5_agent/scripts_dc3pa/stage0_audit.py --repo-root . --output runs/stage0_audit.json`: wrote 48 findings.
- `cd MP5_agent && python -m pytest -q` using the existing `MP5_agent` conda environment: `34 passed in 0.52s`.
- `python -m pytest -q MP5_agent/tests_dc3pa/test_dependency_memory.py MP5_agent/tests_dc3pa/test_exemplar_memory.py MP5_agent/tests_dc3pa/test_freeze_redaction.py MP5_agent/tests_dc3pa/test_config_and_launcher.py MP5_agent/tests_dc3pa/test_repo_specific_integration.py` using the existing `MP5_agent` conda environment: `19 passed in 0.18s`.
- Workflow validation/round-trip smoke: passed; legacy round-trip remained Controller-compatible.
- Stage 2 memory demo smoke: passed; learned `wooden pickaxe -> cobblestone` as a tool dependency and retrieved one scene exemplar.
- Baseline launcher `--dry-run` with real task JSON path: passed; launch preview redacted credential-like variables and recorded world seed, simulator seed and `PYTHONHASHSEED`.

## Audit Summary

`runs/stage0_audit.json` contains 48 findings from legacy source audit. The findings are expected Stage 0 provenance records, not all newly introduced defects.

High-signal findings include:

- Direct inventory mutation in legacy runner/controller, including `self.env.set_inventory([])` and controller fallback inventory updates.
- Task-specific diamond/redstone branches and fixed redstone workflow text in legacy sources.
- Planner prerequisite injection code, now gated for research-clean mode.
- Fallback behavior in the legacy Controller, still present for legacy comparisons.

## Verified Acceptance Points

- Legacy mode remains selectable through feature flags.
- Guarded patch is idempotent after repository-specific exact-anchor support.
- `dc3pa_feature_flags.py` is importable when launched from `MP5_agent/agent`.
- Cold-start scene retrieval returns an empty list without error, covered by exemplar memory tests.
- Successful cobblestone memory demo learns `wooden pickaxe -> cobblestone` tool dependency.
- Failed episodes cannot add dependency edges or scene exemplars, covered by memory tests.
- Scene retrieval ranks closer vectors above orthogonal vectors, covered by exemplar memory tests.
- Run manifests exclude `OPENAI_API_KEY`; launch previews redact credential-like variable names.
- Launcher records and applies `DC3PA_WORLD_SEED`, `DC3PA_SIM_SEED`, and `PYTHONHASHSEED`.
- Research-clean mode disables the fixed redstone workflow, planner prerequisite injection, and deep-mining task-hack entry point through `DC3PA_LEGACY_TASK_HACKS=0`.

## Assumptions And Unresolved Risks

- No manuscript PDF was available, so alignment is verified only against `docs/PAPER_ALIGNMENT_STAGE0_2.md`.
- Offline tests were run in the existing `MP5_agent` conda environment because base Python did not have `pytest` installed.
- MineDojo, Minecraft, real LLM calls, MineCLIP and end-to-end task success were not executed for this integration; this task was limited to offline Stage 0-2 verification.
- The legacy audit still reports direct inventory mutation and task-specific text. Known high-level entry points are gated, but the original low-level Controller recovery remains inherited and should be separately audited before formal paper-level experiments.
- Generated smoke outputs containing local absolute paths were intentionally removed before commit; only `runs/stage0_audit.json` is preserved.
