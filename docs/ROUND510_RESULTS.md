# DC3PA Round 5.10 results

## Scope

Round 5.10 used the approved single-chain reactive acquisition path with
Formal Log Bootstrap enabled and Evaluation Chain disabled. The task-set
amendment replaced `mine sand` with `craft wooden pressure plate`.

The formal campaign artifacts are stored outside Git under:

`/external/dc3pa/round510-pressure-plate-gpt4turbo`

No API keys, request bodies, images, databases, traces, or large runtime logs are
committed to this repository.

## Formal acquisition campaign

- Source commit used by the formal audit:
  `bb7469681509968b46e717c777ee782602087968`
- Campaign ID:
  `19e1360233620110ebc5cf1a2af5ace4e1107125a680388a7a7dd2d5ef6aacff`
- Formal acquisition audit ID:
  `c65611a908a1e00d3ec1330f3f27e489b9c5848e2adc9a6b44685756cd2ea8df`
- Acquisition root SHA256:
  `01ab1134830a4663d6cae9b747ecfe4c489fdd21bd51a278ede79face4981292`
- Scheduled episodes: `100`
- Resolved episodes: `100`
- Successful episodes: `40`
- Scientific failures: `60`
- Technical retries: `1`
- Unresolved technical failures: `0`
- Planner calls: `313`
- Reflection calls: `269`
- Evaluation Chain calls: `0`
- Controller executions: `309`
- Successful acquisition records: `40`
- Failed episodes written to acquisition memory: `0`

Successes by task:

- `craft boat`: `2`
- `craft button`: `4`
- `craft chest`: `3`
- `craft crafting table`: `4`
- `craft fence`: `4`
- `craft furnace`: `3`
- `craft stone hoe`: `4`
- `craft stone shovel`: `1`
- `craft stone sword`: `3`
- `craft wooden axe`: `1`
- `craft wooden pickaxe`: `3`
- `craft wooden pressure plate`: `4`
- `mine log`: `4`

## Log Bootstrap

Formal Log Bootstrap was enabled as an execution-side fallback for unstable log
collection. It improved campaign stability by allowing successful trajectories
to proceed after bounded log-collection failures, while preserving ledgered
provenance for bootstrap assistance.

- Bootstrap-assisted completions: `35`
- Natural completions: `5`
- Injected logs: `249`
- Naturally collected logs: `8`
- Intervention triggers: `150`

## Frozen Memory V4

Frozen memory was built only from successful acquisition records. It uses a
standard OpenAI CLIP ViT-B/16 adapter, not MineCLIP, and is not claimed as a
paper-level reproduction.

- Memory contract:
  `dc3pa-round510-pressure-plate-bound-clip-vitb16-chw-text77-memory-v4`
- Contract ID:
  `49b42ee8767dafd6eba8aa37293308637252c96478f39a3bdc286035ad5c2ded`
- Release ID:
  `92bf4512d473addb4beec9a7909428215008ca624d6b802c055b00c15ecea5ce`
- Snapshot root SHA256:
  `53357cba689cfa6ff94f414a7f5e6c39ce1897c4cc5945f33fd6b8c05ca28e3f`
- Database SHA256:
  `ce4fe4269bcf20913726a6c91806257fcd2874ff5f2df181b00ac647e51b5c32`
- Successful episodes included: `40`
- Scene exemplars: `144`
- Dependency edges: `27`
- Structured action-key coverage: `1.0`
- Minimum dependency support: `2`

Read-only smoke:

- Smoke ID:
  `b00072767444ca83c239cf8b5c65eb9d0f34429f73fb026b62e467c407dd428f`
- Eligible: `true`
- Query-only database open: `true`
- Mutation attempt blocked: `true`
- Snapshot root before/after: unchanged

Online scene-only audit:

- Eligible: `true`
- Episodes: `40`
- Scene exemplars: `80`
- Dependency edges: `0`

## Notes

The model returned by the transit provider was not treated as a blocking
eligibility condition for this round, per author instruction. The run used the
configured endpoint and model request values from environment variables only.
