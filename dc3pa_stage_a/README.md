# Stage A 工具包（附加，不改基础代码）

本包为大修方案 Stage A 提供三件工具。**它不修改 `MP5_agent/agent/` 或 `MP5_agent/dc3pa/` 下的任何文件**，只在运行脚本里被引用。

```
dc3pa_stage_a/
├── inventory_write_logger.py   包裹 env.set_inventory，逐次记录直接库存写入
├── paper_config.py             Option-B 论文运行配置：冻结、哈希、一致性断言
├── analyze_stage_a.py          离线分析，产出 Stage A 的四张表
├── test_stage_a.py             14 个测试，无需 MineDojo / LLM / GPU
└── fixtures/                   合成日志，用于离线验证分析逻辑
```

## 安装

放到仓库根目录下（与 `MP5_agent/` 同级），或任何在 `PYTHONPATH` 上的位置。**不要放进 `MP5_agent/dc3pa/`**——保持它与被审计的基础代码物理分离，这样 `git diff` 一眼就能看出基础代码没动。

```bash
python -m pytest dc3pa_stage_a/test_stage_a.py -q   # 期望 14 passed
```

## Option B 的关键事实

三处任务特化路径分属两层，**由两个环境变量分别控制**：

| 路径 | 文件:行 | 层 | Option-B 状态 |
|---|---|---|---|
| `_inject_prerequisite_steps` | `agent/planner.py:75` | **规划层** | **OFF** |
| `_fixed_workflow_for_task` | `agent/run_agent.py:118` | **规划层** | **OFF** |
| deep-mining 资源/合成 fallback | `agent/controller.py:224/257/313` | 执行层 | ON |

```python
# agent/controller.py:37
def _is_deep_mining_task(self, task_information):
    bounded_fallback_enabled = os.environ.get(
        "DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK", "").lower() in {"1","true","yes","on"}
    return task_information.get("task") in {"diamond","redstone","gold"} and (
        legacy_task_hacks_enabled() or bounded_fallback_enabled)
```

两个规划层路径在 `legacy_task_hacks_enabled()` 为假时直接返回原值；控制器路径额外接受 `DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK`。因此：

```bash
export DC3PA_LEGACY_TASK_HACKS=0                        # 规划层两处 OFF
export DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK=1     # 执行层替代 ON
```

**这正是 Option B 需要的切分，纯环境变量，零代码改动。** `paper_config.py` 会强制断言这两个值。

## 1. 记录库存写入

```python
import os
from dc3pa_stage_a.inventory_write_logger import InventoryWriteLogger

env = minedojo.make(...)
logger = InventoryWriteLogger(
    jsonl_path=f"runs/{run_id}/inventory_writes.jsonl",
    context={
        "run_id": run_id, "task": task_name, "tier": tier, "seed": episode_seed,
        "runtime_mode": cfg.mode, "memory_mode": cfg.memory_mode,
        "traversal": traversal,
        "legacy_task_hacks": os.environ.get("DC3PA_LEGACY_TASK_HACKS"),
        "bounded_resource_fallback": os.environ.get("DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK"),
    },
)
logger.install(env)
try:
    ...run the episode...
finally:
    logger.uninstall()
```

要点：

- 原方法始终被调用，参数与返回值原样透传，**行为不变**；
- `granted` 是相对上一次调用的**正向增量**，因为 `set_inventory` 替换整个背包；
- `caller_chain` 记录调用栈，可区分是 `_fallback_mine_diamond_resource` 还是 `ensure_wooden_bootstrap`；
- 它拦截的是**所有**直接库存写入，不依赖某个函数名，所以将来新增路径也会被记录。

## 2. 冻结论文运行配置

```python
from dc3pa_stage_a.paper_config import PaperRunConfig, OPTION_B_ENV

cfg = PaperRunConfig(
    runtime_mode="dc3pa",                    # 对照为 reasoning_only / mp5_legacy
    memory_mode="evaluate_readonly",
    record_legacy_workflow_memory=False,
    record_multimodal_memory=False,
    max_execution_attempts=30,
    env_flags=dict(OPTION_B_ENV),
    acquire_seeds=[...],
    evaluate_seeds=[...],                    # 与 acquire 不重叠，会被断言
)
config_hash = cfg.write("configs/paper_run_config.json")
cfg.export_env()                             # 把两个 flag 写进本进程环境
cfg.assert_process_matches()                 # 运行前再验一次，防止漂移
```

`config_hash` 必须写进每次运行的 manifest。

## 3. 离线分析

```bash
python -m dc3pa_stage_a.analyze_stage_a \
  --inventory-writes runs/stageA/inventory_writes.jsonl \
  --episodes         runs/stageA/episodes.jsonl \
  --output           docs/evidence/stage_a/analysis.json \
  --markdown         docs/STAGE_A_ANALYSIS.md
```

`episodes.jsonl` 每行至少需要：`run_id, task, tier, seed, runtime_mode, memory_mode, traversal, success`。

产出四张表：

| 表 | 回答什么 | 为什么重要 |
|---|---|---|
| A 替代范围 | 哪些任务被触及、各档多少、共发放了什么 | 披露必须精确到任务与物品 |
| B 逐模式对称性 | 三个 runtime mode 各自的调用率 | **Option B 成立的前提**：若 dc3pa 调用更频繁，它拿到更多免费资源，内部对比被混淆 |
| C 顺序不变性 | 正序 vs 逆序的逐 seed 一致率，按 memory_mode 分列 | `acquire` 下预期不一致、`evaluate_readonly` 下预期一致——这张表直接回应记忆泄漏质疑 |
| D 双总体成功率 | 全部任务 vs 替代未触及子集 | **Option B 下最强的稳健性证据**：若结论在未触及子集上同样成立，说明替代不是结论的来源 |

表 B 的 `symmetric_within_10pct` 只是描述性标记，**验收阈值由工单规定，不由本工具判定**。
