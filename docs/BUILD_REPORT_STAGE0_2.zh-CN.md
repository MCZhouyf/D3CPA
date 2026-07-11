# DC3PA 0-2 阶段构建与复核报告

## 交付形态

本交付是可合并到 `MCZhouyf/D3CPA` 本地克隆的 **overlay**，不是整个 Git 仓库快照。这样做是为了避免在没有用户本地提交、依赖和未提交修改信息的情况下武断覆盖原工程。遗留文件只通过带精确锚点、可重复执行、遇到源码漂移即中止的 patcher 修改。

## 第一轮复核：结构、契约与论文边界

复核对象包括当前公开仓库的 `run_agent.py`、`planner.py`、`controller.py`、`work_memory.py` 与动作 prompt，以及论文的多模态记忆设计。

本轮确认并实现：

- 当前工程仍以 MP5 的规划—执行—失败后反思重规划为主；
- Planner、固定 redstone workflow 和深层采矿路径中存在任务特定逻辑，必须通过 feature flag 隔离；
- 原 runner 已支持通过环境变量读取模型名和任务文件，可由 Stage 0 launcher 安全注入；
- 原动作 prompt 的 9 类动作与 Stage 1 schema 对齐；
- Stage 2 只实现依赖图和场景样例，不提前实现 HPM、双链评价或自适应触发；
- 依赖抽取保留显式物品名，例如 `iron ore`，不擅自简化为 `iron`；
- legacy workflow 往返后仍保持 Controller 需要的 `workflow/times/actions/args` 形状；
- legacy workflow 导入必须显式传入 `confirmed_success=True`，避免把来源不明的轨迹默认提升为成功记忆。

第一轮发现并修正的问题：

- JSON 字符串 `"false"` 原本可能被 Python 当作真值，现要求 feature flag 必须是真正的 JSON boolean；
- launcher 原本可能记录配置文件中的空 task/model，而不是 CLI 覆盖值，现 manifest 记录有效配置；
- task 路径原本可能延迟到 legacy runner 才失败，现 dry-run 前即校验；
- 只控制 `world_seed` 不足，现同时控制 MineDojo simulator seed、Python `random`、NumPy 和 `PYTHONHASHSEED`；
- manifest 现从实际子进程环境记录 model/task/seed，同时排除 API key；
- overlay 合并器现跳过 `__pycache__`、pytest cache 和字节码。

## 第二轮复核：失败模式、原子性与实验污染

本轮以“如何让实现产生静默错误”为目标进行逆向检查，而不是默认设计正确。

重点验证并修正：

- memory 写入使用单一 SQLite 事务；依赖边成功写入后若 exemplar 失败，episode、edge 和 exemplar 均回滚；
- 图片已复制但数据库事务失败时会删除新复制文件，避免孤儿样例；
- 不存在的 `image_path` 直接报错，不在数据库中保存坏路径；
- 非有限向量被拒绝；维度不匹配的向量不会被强行相似度比较；
- 失败 episode 无法通过子 store 写入依赖或样例；
- RNG audit 不再把 `random.seed` / `np.random.seed` 本身误报为未控制随机性；
- audit 输出遗留文件的仓库相对路径，降低本机路径泄漏；
- 环境冻结会清除依赖 URL 中的内嵌凭据；launch spec 会按 KEY/TOKEN/SECRET/PASSWORD/CREDENTIAL 通用规则脱敏；
- 原始 Controller 的 `env.set_inventory` 和通用低层恢复仍可能造成实验混杂，本阶段只审计和隔离已知入口，不声称已经彻底清除。

## 已执行验证

- `python -m pytest -q`：**32 passed**。
- `python -m compileall -q dc3pa scripts_dc3pa tests_dc3pa`：通过。
- 在合成的 legacy 仓库夹具上执行 overlay merge：通过，且不会复制缓存目录。
- guarded patch dry-run、正式应用与第二次幂等应用：通过。
- Stage 0 launcher 使用真实存在的任务 JSON 做多 seed `--dry-run`：通过；manifest 中 CLI task/model/seed 与实际 launch 环境一致，已有 run 目录不会被静默覆盖。
- Stage 0 合成执行：stdout、metrics 与本次运行确实更新过的 legacy `agent.log` 均归档到独立 run 目录。
- Stage 1 workflow schema 校验与 legacy round-trip：通过。
- Stage 2 memory demo：成功写入 1 个 episode、4 条显式依赖证据，并检索到 scene exemplar。
- 人工注入 exemplar 序列化失败：数据库和复制图片均完整回滚。

## 尚未声称完成或验证的事项

- 没有在本容器中启动 MineDojo、Minecraft/JDK 后端、真实 LLM 或 MineCLIP；因此不声称端到端任务成功。
- 没有在用户本地 clone 的确切 commit 上直接应用 patch；Codex 必须先执行两轮检查并核对精确锚点。公开 `main` 已通过网页逐文件核查，但本地代码可能已变化。
- `controller_low_level_recovery` 已进入配置和 manifest，但尚未贯穿 Controller 的所有恢复分支；文档明确标记这一限制。
- 原 Controller 的任务特定 fallback、直接 inventory mutation 和底层动作实现需要在进入论文级正式实验前继续做 provenance audit。
- Stage 3 的 Hybrid Probability Model、Evaluation Chain 和 Adaptive Trigger 完全未实现。

## 结论

0-2 阶段达到“可独立测试、可审计、遇到源码漂移不猜测”的交付目标，但它仍是安全的集成基础，不是论文完整复现。下一步应由 Codex 在用户本地仓库按提示词先核对，再合并和运行，而不是直接覆盖遗留源码。
