# CodeScan 开发计划（待开发）

> 更新时间：2026-11-17  
> 状态：P1 分析器质量与回归已完成；本文件只记录后续待开发项，不重复已完成能力。

## 当前基线

已完成：

- 21 类分析器（17 接口级 + 4 仓库级）；
- 85 个分析器 fixture，21/21 类覆盖；
- demo v1/v2/fresh-clinic 回归与基线；
- 矩阵状态机、结构化 planner 补派、完成门禁；
- 人工强制审计、人工添加漏洞类型；
- SQL 注入特征关联（`${}` / 拼接 / raw wrapper，纯 `#{}` 不派）；
- `scope=pattern` 跨接口模式复核；
- 对单接口 worker 观察的 `scope=repo` 扩展拦截；
- 用户可见品牌改为 CodeScan（图标暂未更换）。

---

# P0 · GitLab 项目增量变更预览

## P0-0 增量变更预览

**状态：** 未开始（设计已记录在 `codeaudit/GITLAB-PROJECT-PLAN.md` 阶段 2.5）

目标：在项目详情页展示 base→target 的提交、变更文件、行数、hunk 和候选接口，让安全工程师决定是否发起增量审计。

验收：

- 文件变更、新增/删除/重命名、+/- 行数、hunk 行号准确；
- 能展开查看 GitLab compare diff；
- 直接/候选/无法映射接口明确区分；
- 无 base、无变更、compare 超时、diff 截断均有明确提示；
- 预览不下载完整源码、不创建任务、不启动 LLM。

**附带修正：** 当前全量审计在任务创建成功后就回写 `last_audited_commit`，不是等审计真正完成。任务失败时会留下“假基线”，影响后续增量判断。实现增量审计前，应改为任务成功/矩阵完成后回写。

---

# P0 · 结果可信度收口

## P0-1 任务 18 finding 复核

**状态：** 未开始

任务 18（fresh-clinic）已产出大量 confirmed/clean 结果，但尚未系统复核。

工作：

- 逐条复核 confirmed finding；
- 判断 confirmed / duplicate / false_positive；
- 合并同根因 finding；
- 回填矩阵格状态；
- 处理 4 个 unverified 格；
- 记录复核依据和源码位置。

验收：

- 所有 confirmed 都有人工复核记录；
- 重复项已合并；
- 误报格已回填；
- unverified 有明确处置；
- 报告中的 finding 与矩阵格一致。

## P0-2 任务 16 / 17 历史 finding 收口

**状态：** 未开始

工作：

- 跨任务去重；
- 重点处理已知重复项（如 136 / 141 / 148）；
- 保留支付回调 finding 147 作为 authn 回归样本；
- 对历史误报回填状态；
- 区分“旧流水线结果”和“新基线结果”。

验收：

- 历史 confirmed 不再存在未处理重复项；
- 新任务不重复报告旧 finding；
- 旧任务结论可追溯。

## P0-3 矩阵状态一致性审计

**状态：** 未开始

任务 18 中出现过：

- `applicable` 数量与已结算状态数量不完全一致；
- 人工补派/探测意图可能改变 eligibility/status；
- 完成门禁看到的状态需要可解释。

工作：

- 检查 `ca_cells` 的 `eligibility`、`status`、`verdict` 组合；
- 找出非法状态组合；
- 修复人工补派、planner 补派后的状态迁移；
- 增加状态一致性测试。

验收：

- 不存在 `not_applicable + confirmed` 等非法组合；
- 完成门禁统计与矩阵 UI 一致；
- 人工补派后状态可解释。

---

# P1 · Worker 输出与停止规则

## P1-1 单轮输出上限

**状态：** 未开始

工作：

- 限制单轮输出 token；
- 工具结果只保留关键片段；
- 事实摘要只写一次；
- verdict 前禁止重复整段分析。

验收：

- 单格输出明显下降；
- 不出现大段重复证据；
- finding 证据仍保持完整。

## P1-2 停止规则

**状态：** 未开始

工作：

- 找到 sink + 可控输入 + 缺失校验 → 停止并提交 verdict；
- 找到正向校验且路径闭合 → 停止判 clean；
- 连续两轮无新增事实 → 停止判 needs_more；
- 禁止为了“再确认一下”全仓扫描；
- 禁止写笔记文件。

验收：

- `exhausted` 比例下降；
- 每格工具调用和轮次可统计；
- clean 必须有正向证据；
- needs_more 必须说明缺什么。

## P1-3 读预算硬限制

**状态：** 未开始

当前部分预算仍主要靠 prompt 约束。

工作：

- 额外 Read 数量硬限制；
- Grep/Glob 次数硬限制；
- 单格工具调用总数上限；
- 超限返回 needs_more，而不是继续探索。

验收：

- 预算在 harness 层生效；
- 不能通过换工具绕过；
- worker 能正确写回 needs_more。

## P1-4 存量 agent prompt 同步

**状态：** 未开始

代码默认提示词已更新为 CodeScan 和新补派规则，但数据库 `agent_prompts` 已种子的内容不会自动覆盖。

工作：

- 检查现有 planner/worker/mainagent/prompt 中的旧品牌名；
- 同步 `scope=pattern`、单接口聚焦规则；
- 提供显式“重置默认提示词”操作；
- 不覆盖用户已编辑的提示词，提供确认流程。

验收：

- 新任务默认提示词为 CodeScan；
- 存量任务可手动升级；
- 提示词版本历史可追溯。

---

# P1 · 分析器残余问题

## P1-5 SQL 分析器边界增强

**状态：** 未开始

已完成特征模型，但仍有：

- `Statement` 与 `PreparedStatement` 接收者类型未严格区分；
- 多行 Wrapper 调用只读取调用行；
- 局部变量追踪仍是启发式；
- `@SelectProvider` 只能 unknown；
- 直接 JDBC 的 SQL 字面量提取还不完整。

工作：

- 识别 JDBC 接收者类型；
- 支持多行 Wrapper 参数；
- 增强局部变量常量传播；
- 补 provider/动态 SQL 测试。

验收：

- 纯 `PreparedStatement + ?` 稳定无特征；
- 动态模板稳定 possible；
- provider 稳定 unknown；
- 新增 fixture 覆盖。

## P1-6 仓库级分析器误报收口

**状态：** 未开始

重点：

- `secrets`：测试值、示例配置、占位符；
- `crypto`：MD5 校验和 vs 密码哈希；
- `sensitive_data`：脱敏、日志、JSON 返回；
- `dependency`：版本命中只作候选。

验收：

- 每类有误报对照集；
- demo 语料无新增误报；
- 真实语料抽样误报率有记录。

---

# P2 · 交付能力

## P2-1 仓库级 finding 独立面板

**状态：** 未开始

工作：

- secrets / crypto / dependency / sensitive_data 分组；
- 每条 finding 显示文件、行号、证据、置信度；
- 支持人工发起复核；
- 与矩阵 REPO 行联动。

验收：

- 不再只依赖矩阵 REPO 行展示；
- 仓库级问题可筛选、可导出。

## P2-2 报告导出

**状态：** 未开始

工作：

- 任务范围、源码版本；
- 接口清单与权限；
- 矩阵覆盖率；
- confirmed finding；
- clean 正向证据摘要；
- needs_more 缺口；
- 仓库级风险；
- 方法与限制说明。

格式：

- 先 Markdown / HTML；
- PDF 后置。

验收：

- 报告内容与矩阵/finding 一致；
- 可交付给非平台用户阅读。

## P2-3 证据包导出

**状态：** 未开始

工作：

- finding 源码片段；
- 文件:行号；
- 调用链；
- 复测报文（非证据）；
- 修复建议；
- 关联矩阵格。

验收：

- 单条 finding 可独立交付；
- 证据不依赖平台会话。

## P2-4 更换 CodeScan 图标

**状态：** 等待素材

工作：

- 替换 `web/src/app/favicon.ico`；
- 替换 `web/src/app/icon.png`；
- 替换 `web/public/logo.png`；
- 同步 `web/public/logo.svg`。

当前只改了名称和标题，图标未换。

---

# P2 · 评测泛化

## P2-5 独立 v3 holdout

**状态：** 未开始

工作：

- 按 `DEMO-SPEC.md` 盲写 v3；
- 不看规则、不看历史结果；
- 只跑不调；
- 统计：
  - 方向召回；
  - 误派率；
  - N/A 误杀；
  - unknown 比例；
  - worker 确认准确率；
  - token / 格；
  - 轮次 / 格。

验收：

- v3 作为 holdout；
- 不把 v3 结果用于调参；
- 与 demo v1/v2 比较泛化差异。

## P2-6 依赖分析真实数据

**状态：** 未开始

工作：

- 接入 OSV / NVD 离线数据；
- 版本区间匹配；
- 调用点可达性；
- 入参可控性；
- 与 dependency finding 分离“版本命中”和“可利用”。

验收：

- 纯版本命中只能 needs_more；
- 有调用证据才可 confirmed；
- 数据缓存可更新。

---

# P3 · 中期能力

## P3-1 增量审计

- 按 commit diff 只重建受影响文件；
- 受影响方法调用方一跳传播；
- 旧版本结论保留；
- 新版本只重跑受影响矩阵格。

## P3-2 多语言 / 多框架

- 当前 Java/Spring/MyBatis 优先；
- 后续评估 Go / Python / Node；
- 分析器契约保持不变：只做结构特征。

## P3-3 失败与重试闭环

- blocked / exhausted / dispatched 无 verdict 的状态迁移；
- 重试上限；
- 避免重复 finding；
- 人工介入入口。

## P3-4 合并派发评估

- 单格派发；
- 同接口多类型合并；
- 同调用链合并；
- 在 fixture 和 worker 稳定后再评估。

## P3-5 CI / 部署

- 本地一键回归已具备；
- 增加 CI 任务；
- 前端静态构建 + Go 二进制发布；
- 数据库迁移和回滚检查。

---

# 暂不处理

以下问题已讨论，但本轮不作为待开发项：

- 其他分析器继续采用“sink + 接口输入”的召回优先策略；
- SSRF / command-exec / path-traversal / xss 等参数级特征收窄；
- 仅在没有明显误派率数据前，不提前改成 SQL 同样的特征模型。

如果后续统计显示某类 `possible` 明显过高，再单独立项。
