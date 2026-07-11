# DC3PA Stage 3–5 paper-alignment boundary

This overlay implements the decision-regulation core described in Sections 4.3.1–4.3.3 and Appendix C of the supplied manuscript. It deliberately stops before Minecraft runtime integration.

## Stage 3 — Hybrid Probability Model

Implemented:

- Knowledge-driven reliability `pK` as a binary prerequisite check over:
  - explicit action-schema requirements; and
  - the Stage-2 Learned Dependency Schema.
- Model-driven reliability `pL` through a provider-neutral verbal-confidence interface with strict `[0,1]` parsing, concise reason capture, and plan-version-aware caching.
- Environment-driven reliability `pE` using the manuscript formula:

  `pE = Smax * (alpha + (1 - alpha) * R)`

  where `Smax` is the highest normalized visual cosine similarity and `R` is text/task relevance for that same best visual exemplar.
- Reliability fusion:

  `Pi = wK * pK + wL * pL + wE * pE`

- Cold start: `wK=0`, `wE=0`, `wL=1`.
- Learned knowledge/environment weight cap: `0.4` each.
- Availability-aware renormalization when a positive-weight provider is unavailable. A zero-weight cold-start signal is never promoted merely because the model provider failed.
- Hard prerequisite conflicts remain visible even in model-only cold start.

### Explicit uncertainty

The manuscript reuses the symbol `alpha` for visual fusion and memory-weight growth but reports only the visual value `alpha=0.7`. This overlay therefore names the second coefficient `memory_weight_growth` and sets an **engineering default of `0.02`**. This value is configurable and must not be presented as a paper-reproduced hyperparameter without the authors' original experiment configuration.

The model confidence interface implements verbal confidence, not hidden logits or calibrated probabilities. Its score quality therefore depends on the external provider and prompt/model calibration.

## Stage 4 — Dual-Chain Architecture

Implemented:

- A provider-neutral Reasoning Chain interface inherited from Stage 1.
- A structured Evaluation Chain that returns exactly one explicit outcome:
  - accept the current plan after detailed evaluation;
  - apply incremental edits;
  - replace the full plan; or
  - request a full replan.
- Atomic, stale-version-protected plan edits: insert before/after, replace, and delete.
- A high-frequency planner with fixed `M=1` reliability monitoring.
- Re-evaluation from the earliest modified step after each revision.
- A configurable maximum revision count to prevent revision loops.
- Hard knowledge conflicts cannot be silently overridden by an `accepted=true` evaluator response.

In this implementation, the Hybrid Probability Model monitors every scheduled step/window. The more expensive Evaluation Chain is called when the monitored score is low, a signal is unavailable under the configured policy, or a hard prerequisite conflict exists. This follows the staged design approved for this repository and must be documented when comparing against any interpretation in which the Evaluation Chain itself runs unconditionally at every `M`.

## Stage 5 — Adaptive Triggering Mechanism

Implemented defaults:

- threshold `tau=0.8`;
- initial evaluation interval `M=3`;
- sliding window size `3`;
- interval adjustment `+1/-1`;
- minimum interval `1`;
- configurable maximum interval.

Behavior:

- low confidence decreases `M`;
- high confidence increases `M`;
- a hard prerequisite conflict immediately sets the next interval to `1`;
- unavailable reliability is treated as uncertainty;
- after plan revision, the next check is forced to one step;
- confidence history from the superseded plan version is cleared.

The manuscript describes the direction of interval adjustment but does not fully specify window size, increment magnitude, maximum interval, or revision-reset behavior. These are explicit, configurable engineering decisions rather than claimed paper constants.

## Not implemented in this overlay

- wiring the new planner into `agent/run_agent.py`;
- real GPT/OpenAI/Gemini/DeepSeek provider adapters;
- MineCLIP runtime loading or image acquisition from MineDojo;
- Controller execution feedback and successful-memory writeback;
- end-to-end Minecraft experiments, paper table reproduction, latency/token accounting;
- ALFWorld integration.

Those items belong to Stage 6 or later. Offline tests and demos do not establish Minecraft end-to-end success.
