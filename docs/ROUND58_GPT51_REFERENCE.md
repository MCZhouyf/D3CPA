# DC3PA Round 5.8: GPT-5.1 reference design

Round 5.8 adds an explicit, reproducible reference configuration without
changing the DC3PA reliability formula, Trigger, Controller actions, or legacy
default provider.

## Reference design

The external input is the manuscript's existing 50-task catalog with columns
`task,difficulty,minimum_subgoals`. The repository contains only an empty
template. The generator pairs horizon-adjacent tasks within each difficulty,
uses frozen SHA-256 salts for covered/held-out and development-role assignment,
and derives disjoint positive integer seeds for final, acquisition, and
development stages.

The design requires exactly ten tasks per difficulty, chooses five covered and
five held-out tasks per difficulty, creates 1500 final seeds, 100 acquisition
episodes, and 45/15/15 development episodes. Final-held-out tasks never enter
acquisition or development. Any catalog, salt, count, task-role, or train/tune
policy change creates a new design and requires new author approval. Outcomes
must never be used to alter final status or final seeds.

Generate the pack outside the repository:

```bash
python scripts_dc3pa/generate_gpt51_reference_design.py \
  --task-catalog /external/final_task_catalog.csv \
  --source-commit COMMIT_SHA \
  --output-dir /external/reference-pack
```

Review the generated files, then pass the CSV/JSON artifacts through the Round
5.7 author-decision compiler and Round 5.6 Blueprint approval flow. Generated
task lists, seeds, prompts, approvals, traces, probe reports, and credentials
must remain external to Git.

## Model profile

`--model-profile gpt51_reference` selects the exact snapshot
`gpt-5.1-2025-11-13` through the Responses API with low reasoning effort,
`store=false`, a 180-second timeout, and three retries. The request sends no
temperature or top-p. Planning, confidence/evaluation, and reflection use the
same snapshot and effort with purpose-specific output caps. The profile requires
`OPENAI_API_KEY`; `OPENAI_BASE_URL` is optional and both remain environment-only.

The launcher records only profile ID, model, effort, call count, and token-usage
scalars. It does not record prompts, responses, or credentials. Provider or
snapshot failures are raised without alias fallback. Omitting `--model-profile`
keeps the legacy ChatOpenAI path unchanged.

## Seed proof

For an approved GPT-5.1 real-experiment launch, the positive integer experiment
seed is passed to both `minedojo.make(seed=...)` and
`minedojo.make(world_seed=...)`. The Evaluator exposes the applied constructor
values, Stage6 fails closed on a mismatch, and the trace records requested and
effective scalar values. The `minedojo`-marked integration test imports the real
legacy stack and verifies the constructor boundary separately from hosted CI.

## External checks

Run the API probe only in the credentialed external environment. Its report
contains no prompt or response text:

```bash
python scripts_dc3pa/probe_gpt51_profile.py \
  --purpose planning \
  --output-report /external/probes/gpt51-planning.json
```

Hosted CI mocks network behavior and does not call OpenAI or MineDojo. A green
hosted gate proves engineering integration only; it is not evidence of API
snapshot availability, MineDojo world startup, task success, or author approval.
