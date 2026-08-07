# Execution-label semantics

`y_exec` is derived from Controller start/finish telemetry and environment
feedback, never from LLM self-assessment or final episode outcome.  A submitted
action with confirmed success has `y_exec=1`; a submitted, confirmed failure has
`y_exec=0`.  `skipped_satisfied`, `system_error`, and `aborted` actions are not
eligible and have `y_exec=null`.  `failure_mode` is deterministic: missing
requirements map to `knowledge_gap`, no observed yield/unreachable targets to
`environment_mismatch`, controller errors to `controller_failure`, step limits
to `budget_exhaustion`, and relay/network/parse failures to `system_api_error`.
Unclassifiable failures remain `unknown`.
