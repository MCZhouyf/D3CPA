# Protected log callback boundary

G0 preserves the existing delayed log callback exactly as found at
`success-finish` commit `06a708e2dcfc6bb83d48e41b1475cf0581db15d5`.

Protected Controller symbols:

- `_LOG_CALLBACK_DELAY_STEPS`
- `_sync_memory`
- `_set_inventory_from_memory`
- `_begin_log_callback_window`
- `_log_callback_due`
- `_complete_log_callback_window`
- `_gather_logs`

The protected inventory write is `env.set_inventory(...)` inside
`_set_inventory_from_memory`; its guard only permits a `log_callback` write whose
sole override is `log`. `_gather_logs` owns the 100 real-environment-step delay
and invokes that protected write. `_sync_memory` is shared with normal execution,
so it is protected and will not be changed; prohibited callers must instead be
removed or disconnected.

`scripts/g0_verify_log_callback_unchanged.py` compares the baseline and current
normalized ASTs and the protected internal call expressions. The corresponding
machine-readable manifest is `runs/g0/log_callback_protected_manifest.json`.
