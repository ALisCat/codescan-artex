# matrix v2 待办 / 已知缺口

| # | 问题 | 状态 | 优先级 | 记录 |
|---|---|---|---|---|
| 1 | planner 通过 `add_intent` 生成的意图没有 `cases/hints`，会绕过矩阵格式、全项目阅读 | **已实现渲染器兜底**（范围提取 + strict overview）；残留：结构化 targets / global 预算 | P1 | MATRIX-DESIGN §32.6 |
| 2 | 跨文件/未解析的守卫 helper 没有显式 `guard_helpers` file:line，可能漏掉归属校验 | **已实现 v0.1**：语义扫描 + authz_model + guard_helpers；残留：未解析 helper 的参数级解析 | P1 | MATRIX-DESIGN §34 |
| 3 | 读预算目前只是 prompt 约束，没有 harness 硬限制 | 待设计 | P2 | — |
| 4 | output token 未下降（新流水线 73k/137k vs 旧 62k/89k） | 待分析 | P2 | MATRIX-DESIGN §31.6 |
| 5 | `max_turns` 目前是全局 15，未按漏洞类型区分 | 待设计 | P2 | — |
| 6 | `unknown` 复用平台 `unverified` 状态，没有独立 DB 状态 | 待定 | P3 | MATRIX-DESIGN §31 |
| 7 | 旧任务里由"守卫 hold"产生的格子未迁移 | 待定 | P3 | — |
| 8 | 图构建的 Java 侧包前缀统计写死 `com.hezhan`（只影响 stats） | 待修 | P3 | — |
| 9 | 分析器单测 / fixture 尚未建立 | **部分**：authz fixture（任意命名/返回值/注解/业务校验）；其余分析器待补 | P2 | MATRIX-DESIGN §34.5 |

## 建议顺序

1. 先收口 planner 意图（§32）：
   - 优先级最高，因为它会让新 worker 重新全项目读；
   - 最低成本方案：从 summary 提取 `*.java` / `/api/...` 作为范围。
2. `guard_helpers`（§34）v0.1 已做：
   - 语义扫描不依赖方法名；
   - 残留：未解析 helper 的参数级解析、`&&`/`||` 分支覆盖、布尔 helper 的调用方约束。
3. 流程稳定后，再考虑读预算、max_turns、output token。
