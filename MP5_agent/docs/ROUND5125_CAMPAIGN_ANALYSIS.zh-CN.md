# DC3PA Round 5.12.5 实验总体分析

## 1. 范围与数据边界

- 源代码提交：`35472b9cd8515b6d9cf6d81321c19de09730274f`。
- 正式 holdout 计划包含 15 个 assignment，正式 ledger 在接受 10 个结果后因供应商技术失败停留在 `claimed`，没有生成标准正式汇总。
- 正式部分使用 `max_explore_steps=120`；其结果目录为 `holdout-35472b9`。
- 剩余 5 个 assignment 采用单独授权的诊断续跑，使用 `max_explore_steps=360`；其结果目录为 `continuation-explore360-35472b9`。
- 续跑结果明确排除在被中断的正式 ledger 汇总之外。因此，下文的 15-run 合并数字只能作为观察性分析，不能表述为一个完整、同协议的正式 holdout 结果。

## 2. 核心结果

| 数据范围 | 有效 pipeline | 任务成功 | 成功率 | 规划调用 | 反思调用 | Controller 执行 |
|---|---:|---:|---:|---:|---:|---:|
| 正式已接受部分 | 10/10 | 9/10 | 90% | 29 | 7 | 16 |
| 360 步诊断续跑 | 5/5 | 0/5 | 0% | 20 | 20 | 20 |
| 观察性合并 | 15/15 | 9/15 | 60% | 49 | 27 | 36 |

`pipeline_pass` 仅表示协议、追踪和 receipt 完整，不表示 Minecraft 任务成功。

按任务统计：

| 任务 | 成功/运行数 | 结论 |
|---|---:|---|
| craft wooden pressure plate | 3/3 | 稳定完成 |
| craft wooden pickaxe | 3/3 | 完成，但均依赖 Log Bootstrap |
| craft stone hoe | 3/3 | 完成，但均依赖 Log Bootstrap |
| craft iron bars | 0/3 | 未跨越工作台、石镐和铁矿链 |
| obtain diamond | 0/3 | 未稳定跨越工作台、圆石和铁矿前置链 |

结果呈现明显的难度断层：前三类基础/石器任务为 9/9，iron bars 与 diamond 为 0/6。当前数据不支持“复杂技术链已经跑通”的结论。

## 3. Log Bootstrap 与 Memory

- 15 个有效结果共注入 54 个 bootstrap logs，自然采集 7 个 logs。
- 9 次成功中，8 次标记为 `bootstrap_assisted_completion=true`，仅 1 次是自然完成。
- 续跑 5 个失败任务共注入 32 个 logs，但仍全部失败，说明 bootstrap 能帮助基础启动，却不能替代稳定的执行层。
- `acquisition_write_count=0`，`formal_memory_write_count=0`。本轮保持 Memory 只读，没有把失败 episode 写入正式 Memory。

因此，本轮成功率主要反映“只读 Memory + Log Bootstrap + Controller”的组合能力，不应解释为无辅助的自然完成率。

## 4. 失败模式

六个科学失败的最终原因：

1. `iron bars / 728276410`：4 轮均未在探索预算内找到 iron ore。
2. `iron bars / 887104140`：前期已获得 24 cobblestone 和 furnace，随后无法稳定合成 stone pickaxe，最终无法接近 crafting table。
3. `iron bars / 1634555087`：先后出现 crafting table 缺失、furnace 合成失败和 stone pickaxe 合成失败。
4. `diamond / 2118196974`：多轮状态推进不连续，最终在有圆石和木材时仍无法通过工作台合成 wooden pickaxe。
5. `diamond / 994922733`：曾进入 iron ore 搜索阶段，最终因 cobblestone 连续采集失败结束。
6. `diamond / 762195504`：长期停留在 2 cobblestone，最后出现背包记录有工作台但执行时判定没有 crafting table。

最终失败可归为：工作台放置、接近、回收或复用 4/6；cobblestone 采集 1/6；iron ore 搜索 1/6。若按整个轨迹而非最终错误统计，工作台和基础资源问题在更多任务中重复出现。

## 5. 预算与 LLM 稳定性

- 将探索预算由 120 增至 360 没有使 5 个剩余任务成功。
- 360 步确实让部分运行获得更多 cobblestone 或进入更深阶段，但也出现无有效工具时重复探索的情况。单纯增加预算会放大 Controller 状态错误，不能修复工作台或工具链问题。
- 续跑的 20 次规划和 20 次反思均成功，trace 中 `llm_call_failed=0`；失败不是由续跑期间的 LLM 请求故障导致。
- 正式 campaign 的中断来自后续 assignment 的供应商技术失败；这解释了 ledger 未完成，但不解释已经形成有效 receipt 的六个科学失败。
- Evaluation Chain 本轮保持关闭，`evaluation_chain_calls=0`。本轮不能用于评价 Evaluation Chain 或完整 DC3PA 双链机制的收益。

## 6. 总体判断

本轮完成了 15 个 assignment 的观察性结果采集，但没有完成一个同协议、可正式封存的 15-run holdout campaign。协议完整性、只读 Memory 和失败不写入约束得到保持；续跑阶段的模型调用也稳定。主要负面结论是：Controller 尚不能可靠维持跨阶段 Minecraft 状态，复杂任务在进入铁器链之前就被工作台、工具合成和圆石采集问题截断。

下一步应先修复并真机验证以下执行不变量，再新建授权 campaign，而不是修改现有 ledger：

1. 明确区分“工作台在背包”“工作台已放置”“工作台可达”，并保证放置、复用和回收状态一致。
2. 对 wooden/stone pickaxe 和 furnace 建立合成后的库存增量验证，失败后不要丢失已有平台状态。
3. 修复 cobblestone 的接近、装备和采集闭环，避免在库存不足时进入后续技术链。
4. 工具链稳定后再单独验证 iron ore 的 120/360 步探索差异。
5. 仅重跑 6 个 hard/complex assignment，并将其作为新的、协议一致的实验，保留本轮结果作为失败基线。
