# DC3PA Round 5.12.2 Development Campaign Results

## 状态与范围

Round 5.12.2 的 60 个 development task-seed 单元已全部形成有效科学结果，
无 pending 单元。最终结果为 36 次成功、24 次 scientific failure，任务成功率
为 60.0%。这是 development evidence，不是 holdout 或 final evaluation 结果；
holdout、最终评估、Fusion 拟合和正式 acquisition 均未在本轮执行。

本结果通过多次受授权的续跑形成，并非单一源码、单一 Controller 和单一预算下的
干净 60-run：38 个有效单元绑定源码 `804c96a027e54f8d93f71299afeec202252d11a2`，
15 个绑定 `5b2f8da7bf8e07a102d65d2dd926ae51a2eba9c3`，最后 7 个 pending
单元绑定 furnace 修复提交 `6f47526b76d8534f8980f0afe2e36142eed2f136`。
因此，不应将聚合成功率解释为单一版本的可复现性能指标。

## 最终汇总

- 完成单元：60/60
- 成功：36/60（60.0%）
- Scientific failure：24/60（40.0%）
- Pending：0
- 被成功续跑替换的旧失败：1
- `dev_train`：27/45 成功（60.0%）
- `dev_tune`：9/15 成功（60.0%）
- 有效 decision records：681（train 528，tune 153）
- Evaluation Chain calls：按协议为 0；被动 confidence 收集产生的模型调用不计入
  Evaluation Chain
- Effective summary ID：
  `1fe72de9841ead5ce16565731b25a6a7523f67468e3557b3c821200e2b32bd6c`

| 难度 | 成功 | 总数 | 成功率 |
| --- | ---: | ---: | ---: |
| Basic | 12 | 12 | 100.0% |
| Easy | 12 | 12 | 100.0% |
| Medium | 12 | 12 | 100.0% |
| Hard | 0 | 12 | 0.0% |
| Complex | 0 | 12 | 0.0% |

| Task | 成功 | Runs |
| --- | ---: | ---: |
| craft boat | 3 | 3 |
| craft button | 3 | 3 |
| craft cauldron | 0 | 3 |
| craft chest | 3 | 3 |
| craft compass | 0 | 3 |
| craft diamond axe | 0 | 3 |
| craft fence | 3 | 3 |
| craft furnace | 3 | 3 |
| craft iron trapdoor | 0 | 3 |
| craft piston | 0 | 3 |
| craft redstone torch | 0 | 3 |
| craft shears | 0 | 3 |
| craft stick | 3 | 3 |
| craft stone shovel | 3 | 3 |
| craft stone sword | 3 | 3 |
| craft wooden axe | 3 | 3 |
| mine coal ore | 3 | 3 |
| mine log | 3 | 3 |
| mine wheat seeds | 3 | 3 |
| smelt iron ingot | 0 | 3 |

## 失败分析

下表按每个失败单元最后一次 Controller feedback 归类。它描述最终阻塞点，
不代表 Episode 中只发生过这一类错误。

| 最终阻塞类别 | 数量 | 主要表现 |
| --- | ---: | --- |
| 资源搜索 | 8 | iron ore、stone 或 cobblestone 在预算内未找到 |
| 合成或工作台 | 8 | stone pickaxe、furnace 或 wooden pickaxe 未合成 |
| 材料或工具不足 | 6 | log、iron ore 数量不足 |
| 导航 | 1 | 无法接近 iron ore |
| Controller exception | 1 | strict equip mask 拒绝 equip air |

最常见的精确最终反馈为：iron ore 搜索失败 5 次、stone pickaxe 合成失败
4 次、furnace 合成失败 3 次。Hard/Complex 的 0% 成功率表明执行侧在地下
资源搜索、工作台复用和长材料链上仍不稳定，不能据此宣称这些任务已解决。

正式根目录中记录了 18 个未被接受的技术尝试：13 个 infrastructure timeout、
2 个 provider transport failure、1 个 provider empty response、1 个 process crash，
以及 1 个历史 unclassifiable failure。该 unclassifiable failure 位于原始
`craft iron trapdoor:1` attempt-0，说明“所有技术失败均在源头可分类”的目标并未
对整条历史证据链完全满足；最终 60 个单元虽均有 accepted scientific outcome，
但此缺口仍需保留为审计限制。

## Furnace Controller 修复

提交 `6f47526b76d8534f8980f0afe2e36142eed2f136` 修复了狭窄矿井内创建
工作台侧向壁龛时的射线方向：Controller 先俯视清除 body voxel，确认 solid
floor，再对地面顶面执行放置。真实 MineDojo 定向烟测从 crafting table 1 和
cobblestone 8 开始，最终得到 furnace 1；完整离线测试为 574 passed、2 skipped。

随后仅重跑 4 个被判定为 furnace/工作台放置因果失败的 task-seed。4 个重跑均
形成 scientific failure，因此没有替换有效实验结论。在实际到达 furnace 阶段的
3 个重跑中，均至少一次在有限重试内获得 furnace；最终失败转移到 iron ore 搜索、
材料不足或后续工具合成。该结果支持“furnace 获得稳定性有所改善”，但不支持
“Hard/Complex 任务成功率提高”的结论。

## 预算与版本限制

有效 60 单元使用了三种冻结执行预算：

| `max_explore_steps` | Episode timeout | 有效单元 |
| ---: | ---: | ---: |
| 60 | 1800 秒 | 38 |
| 120 | 1800 秒 | 11 |
| 120 | 3600 秒 | 11 |

预算、源码和 Controller 版本的混合是作者批准续跑产生的已知限制。旧 accepted
证据未删除，两个中断的 diamond-axe 快照保留为 aborted evidence，后续 pending
单元没有重跑已完成的 53 个单元。

## 完整性

- Effective campaign status SHA-256：
  `634289c542a2fb292fd60b3b73209a0de13ab037ed3df98f04d340d19f575cde`
- Effective train JSONL SHA-256：
  `f1336cc0143560695cfc63cbd674e6f230aab16952ec50ee3ba457327e236abd`
- Effective tune JSONL SHA-256：
  `7a04b55d3f345b9e7fb0e6d37f8bd58459f2bb2d7a6f21afb8ac033f79515a0e`
- Pending continuation progress SHA-256：
  `30858c39bea8408de83c6ca0243d766af9985268f501f3613fd767ea3e1b3fdf`
- Furnace repair authorization ID：
  `46e8536a34e7273b80b7ebabf6093cf80f28eed6bcb30c629d723891ad8ea30c`
- Pending continuation authorization ID：
  `fdbd7e9d1e60830db7c2fbec60ae099285f8f976f108c0ec21901f3dd7d5b4f4`

原始 traces、图像、SQLite、decision JSONL、模型响应、运行日志、授权中的机器路径
和凭据均不提交到 Git。仓库只保存 Controller 修复、回归测试和本精简报告。
