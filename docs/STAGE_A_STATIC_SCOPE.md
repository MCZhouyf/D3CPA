# Stage A static substitute scope

This is a pre-registration/static scope table, not an empirical A3 result. The formal task catalog is bound in `configs/stage_a_formal_taskset_manifest.json` (catalog SHA-256 `3b1c8b82461597ea8ad9fbf226fc01b82cb724d96c36dfbf9f0b4d1a9a4f57d`; manifest SHA-256 `14b40f1c6366d84f567e9a30a1b4fca77a05620898560ce70124758c7a364e04`).

`Controller._is_deep_mining_task` (`MP5_agent/agent/controller.py:37-43`) matches only runtime targets `diamond`, `redstone`, and `gold`. The 50 formal creative JSONs have runtime target candidates bound in the manifest. Static matching therefore predicts the following.

| Tier | Formal tasks | Static matches | Fraction |
| --- | ---: | ---: | ---: |
| basic | 10 | 0 | 0% |
| easy | 10 | 0 | 0% |
| medium | 10 | 0 | 0% |
| hard | 10 | 0 | 0% |
| complex | 10 | 2 | 20% |
| all | 50 | 2 | 4% |

| Formal task | Creative JSON target | Static result |
| --- | --- | --- |
| `obtain diamond` | `diamond` | expected to reach the controller substitute gate |
| `mine redstone` | `redstone` | expected to reach the controller substitute gate |
| `craft raw gold block` | `raw gold block` | does **not** match `gold`; not expected to be touched by this gate |

The exact number of invocations and item quantities cannot be inferred honestly from task names. They depend on the generated workflow, execution failures, and current inventory. The additive logger records every direct write, and `analyze_stage_a.py` now counts a substitute only when a positive grant has a controller fallback in its caller chain. Formal Table A must be generated only from those recorded episodes.

The proposed A3 coverage subset contains two tasks per tier and includes both expected matches: `mine log`, `craft button`; `craft chest`, `craft wooden pickaxe`; `mine cobblestone`, `mine iron ore`; `smelt glass`, `craft iron pickaxe`; `obtain diamond`, `mine redstone`.
