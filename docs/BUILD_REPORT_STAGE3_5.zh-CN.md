# DC3PA 第 3–5 阶段构建与复核报告

## 构建基线

本 overlay 面向 GitHub `stage0-2` 标签。生成时公开 release 页面显示该标签指向短提交 `73afe2a`。由于构建容器不能直接克隆远程仓库，代码合并测试使用了第 0–2 阶段实际交付的 overlay，并通过 GitHub 页面抽查了标签、目录和被替换文件。最终 Codex 必须在真实仓库上再次确认标签祖先关系、文件哈希与完整测试，不能把这里的离线模拟当作远程仓库集成已经完成。

## 实现范围

### 阶段 3

- Knowledge/Model/Environment 三维可靠性评分。
- 论文环境公式和加权融合公式。
- 冷启动、经验权重上限、缺失信号重新归一化。
- 基于 Stage-2 memory 的组合工厂。

### 阶段 4

- 结构化 Evaluation Chain。
- accept/patch/replan 互斥结果契约。
- 原子计划编辑、版本防陈旧、修正后强制复检。
- 固定 `M=1` 的高频双链规划器。

### 阶段 5

- 阈值 `0.8`、初始 `M=3` 的自适应触发器。
- 滑动窗口、`M` 增减、硬冲突强制高频。
- 修订计划后清除旧版本置信历史。

## 第一轮复核：论文与架构对齐

检查重点：公式、Stage-2 memory 接口、Stage-1 Plan/AgentState 契约、模块边界以及 Stage-6 范围。

发现并处理的问题：

1. 论文没有给出独立的 memory weight growth 数值，不能把视觉 `alpha=0.7` 武断复用。实现改用明确命名的可配置 `memory_weight_growth=0.02`，并标注为工程默认值。
2. 仅用“无 patch”无法区分“评估确认可接受”和“评估失败”。Evaluation Report 改为严格互斥的 `accepted`、concrete patch、`request_replan` 三类结果。
3. Stage-3 配置存在但若没有工厂容易接线错误，新增 `build_hybrid_probability_model`，统一连接 Stage-2 dependency/exemplar memory。
4. 双链修订后必须从最早变化位置重新验证，并保留 plan ID/version/parent 关系。
5. 明确不修改现有 Minecraft runner、Controller 和真实模型接口，防止提前混入 Stage 6。

## 第二轮复核：失败模式与反例

检查重点：错误类型、provider 故障、缓存、陈旧结果、计划修订、触发状态、序列化和运行脚本。

发现并处理的问题：

1. Python `bool` 会被当作数字，导致 `True` 被接受为 1.0；概率、权重、计数和 interval 现在均严格拒绝 bool。
2. NaN/Inf 可能污染置信度或 inventory；现统一检查 finite。
3. 暂时性模型 provider 故障若被缓存会永久返回 unavailable；现在只缓存成功评分。
4. 计划修订后滑动窗口仍保留旧 plan 置信度会产生陈旧控制信号；现在 revision 时清空历史。
5. Reliability provider 若返回错误 plan ID/version/step，可能驱动错误触发；planner 现在逐项验证对齐。
6. `ReliabilityContext.metadata` 可覆盖真实 image/task 字段；保留字段现在具有最高优先级。
7. Evaluation Chain 不能用 `accepted=true` 静默绕过 hard prerequisite conflict；这种情况被记录为 unresolved。
8. Evaluation JSON 的字符串布尔值、未知 step ID、fractional plan version、重复 edit ID 等均被拒绝。
9. 环境编码器或 exemplar 检索故障不应猜测概率；现在返回 unavailable 并保留简短错误证据。
10. demo 直接以脚本路径运行时最初无法导入 `dc3pa`，已增加相对 `MP5_agent` 的安全导入路径并重新执行。

## 已执行验证

最终打包前需要由自动脚本重新生成具体结果；本报告初始复核已完成：

- Stage 0–5 合并后的离线 pytest：83 项通过。
- 三个离线 demo：通过。
- JSON 配置解析：通过。
- Python compileall：通过。
- 无 MineDojo、真实 LLM、真实 MineCLIP 或网络调用。

最终精确校验结果记录在 `docs/FINAL_VALIDATION_STAGE3_5.txt`。

## 不应作出的结论

这些结果只证明模块级和模拟集成行为，不能证明：

- Minecraft 端到端任务成功；
- 论文中的 SR、RC、PT 已复现；
- verbal confidence 已校准；
- `memory_weight_growth=0.02` 是论文原始实验值；
- 当前 Controller 已经接入新 planner。
