# ARTEX 代码审计平台 · 二开计划书

| 项 | 内容 |
|---|---|
| 版本 | v0.1（草案） |
| 日期 | 2026-10-21 |
| 基线 | ARTEX v0.3.15（git `695f8a1`） |
| 目标语言 | Java（Spring / MyBatis 生态优先） |
| 文档状态 | 待评审 |

---

## 0. 摘要

**一句话**：把 ARTEX 从「AI 渗透测试编排器」改造成「AI 静态代码审计编排器」。

**核心判断**：这次二开的价值不在"加一个扫描器"，而在把 ARTEX 的两项原创能力迁移到代码审计场景：

1. **探索图**（goal / intent / fact / finding / hint + 状态机）→ 变成「审计推理链」
2. **覆盖度驱动**（anchors + `list_untested_*`）→ 变成「审计矩阵」，即 `端点 × 漏洞类型` 的待办看板

**核心改造**：

| 维度 | 现状 | 目标 |
|---|---|---|
| 资产图 | 一棵去重树（无边表） | 代码图（实体 + 类型化边 + 参数级数据流） |
| 分析单元 | 资产 / 服务 / 端点 | **审计线**（source → sink 的完整路径 + 途经守卫） |
| 任务生成 | planner 从图态势推断 | **矩阵枚举**（确定性），planner 只做优先级与补充 |
| 证据 | HTTP 报文快照 | 代码路径 + 行号 + 兄弟方法对照 |
| 判定 | 动态复现 | **静态推断 + 置信度分级** |

**工作量估算**：1 名后端 + 0.5 名前端，约 **13 周**（含 1 周可行性验证，不含业务逻辑视图可选项）。

---

## 1. 目标与边界

### 1.1 做什么

1. 导入 Java 项目，构建**代码图**（结构 + 数据流 + 安全语义）
2. 枚举**审计线**，按 sink 类型确定性分类
3. 生成**审计矩阵**（端点 × 漏洞类型），支持覆盖度追踪
4. 由 Agent 逐格审计，产出**带证据链的 finding**
5. 输出可交付的**代码审计报告**
6. 支持**增量审计**（按 commit diff）

### 1.2 明确不做

| 不做 | 原因 |
|---|---|
| 不做动态验证 / 请求重放 | 属于 DAST，不在代码审计交付范围内 |
| 不替代 Semgrep / CodeQL / Joern 的检测引擎 | 我们做编排与判定，不做扫描器 |
| 不做多请求业务逻辑的完整建模（首版） | 需要状态机视图，放到阶段 6 |
| 不做多租户（首版） | 内部工具定位，先单租户 |
| 不删渗透模块 | 降低与上游合并的冲突，且保留未来闭环可能 |

### 1.3 验收标准（可量化）

| 指标 | 目标 | 测法 |
|---|---|---|
| 建图规模 | 5 万行 Java → ≥1 万实体、≥3 万边 | 导入日志统计 |
| 建图耗时 | 全量 < 10 分钟；增量（100 行 diff）< 3 分钟 | 计时 |
| 端点识别召回 | ≥ 95% | 对照人工标注的 Spring 路由清单 |
| 归属谓词识别准确 | ≥ 90% | 人工抽样 100 条线 |
| 越权类召回 | ≥ 60% | 内部标注集（见 §5 阶段 0） |
| 越权类误报 | ≤ 30% | 同上 |
| 单次全量审计成本 | ≤ ¥150 | LLM 用量统计 |
| 报告可用性 | 每条 finding 含代码路径 + 对照 + 修复建议 | 人工评审 |

> **前置依赖**：需要建设**内部标注集**（见 §5 阶段 0.5）。没有标注集，上述召回/误报指标无法度量，项目会退化成"感觉还行"。

---

## 2. 总体架构

### 2.1 分层

```
┌─────────────────────────────────────────────────────────────┐
│  L4 审计层（ARTEX 探索图，复用）                              │
│  goal → intent(端点, 漏洞类型) → fact → finding              │
└─────────────────────────────────────────────────────────────┘
                            ▲ 锚定
┌─────────────────────────────────────────────────────────────┐
│  L3 审计矩阵（新增）                                          │
│  ca_audit_tasks: 端点 × 漏洞类型 → 状态 / 结论 / 置信度        │
└─────────────────────────────────────────────────────────────┘
                            ▲ 消费
┌─────────────────────────────────────────────────────────────┐
│  L2 安全语义层（新增）                                        │
│  sink 分类 · source 识别 · guard 抽取（注解/谓词/净化）        │
│  ca_lines: source → hops → guards → sink                    │
└─────────────────────────────────────────────────────────────┘
                            ▲ 构建于
┌─────────────────────────────────────────────────────────────┐
│  L1 代码图（新增）                                            │
│  ca_entities (module/package/class/method/field)            │
│  ca_edges (contains/calls/implements/extends/flows_to/...)  │
│  数据来源：Joern CPG（离线导出 JSON）                         │
└─────────────────────────────────────────────────────────────┘
                            ▲
┌─────────────────────────────────────────────────────────────┐
│  L0 源码                                                     │
│  Maven/Gradle 项目 · Java 源码 · MyBatis XML · 配置          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
① Joern 建 CPG（离线，批处理）
        ↓ JSON
② 导入器 → ca_entities / ca_edges
        ↓
③ 规则引擎
   ├─ sink 分类（SQL/file/exec/http/deserialize/bind）
   ├─ source 识别（HTTP param/body/header/principal）
   ├─ guard 抽取（@PreAuthorize / @DataScope / findByIdAndUserId / 净化函数）
   └─ 一致性分析（兄弟方法守卫签名对比）
        ↓
④ ca_lines（审计线：source → hops → guards → sink + 候选类型）
        ↓
⑤ 矩阵生成 → ca_audit_tasks（端点 × 类型）
        ↓
⑥ Agent 逐格审计（复用 ARTEX intent 生命周期）
        ↓
⑦ finding（含置信度 + 证据链）→ 报告
```

### 2.3 与 ARTEX 现有模块的映射

| ARTEX 现有 | 代码审计对应 | 复用方式 |
|---|---|---|
| `assets`（树） | `ca_entities` + `ca_edges` | **替换**（新增表，不动旧表） |
| `exploration_nodes` | 审计推理链 | **原样复用** |
| `exploration_edges` | intent 派生关系 | **原样复用** |
| `planner.go` | 审计调度 | 提示词改写（DB 层），代码微调 |
| `worker.go` | 单格审计执行 | **原样复用** |
| `agent/tools.go` | 领域工具 | 新增代码审计工具，保留旧工具 |
| `intercept` | 工具审批 | 保留（执行命令/读文件时仍需要） |
| `traffic` | — | 隐藏，不启用 |
| `evidence` / 报告 | 审计报告 | 改造渲染层 |
| `llmpool` / `llmrec` | — | **原样复用**（成本监控刚需） |
| `notify` / `selfupdate` / `mcphttp` / `skills` | — | **原样复用** |

> **关键发现**：ARTEX 的提示词由 `agent_prompts` 表驱动（`promptcatalog.go` 幂等播种，运行时可改）。
> 因此 planner / worker 的**语义改造主要是数据变更**，不是代码分叉。这是本项目最大的降风险点。

---

## 3. 数据模型

### 3.1 新增表（`db/codeaudit.sql`）

```sql
-- 代码仓库
CREATE TABLE IF NOT EXISTS ca_repos (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    language    TEXT NOT NULL DEFAULT 'java',
    root_path   TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 代码实体（节点）
CREATE TABLE IF NOT EXISTS ca_entities (
    id          BIGSERIAL PRIMARY KEY,
    repo_id     BIGINT NOT NULL REFERENCES ca_repos(id) ON DELETE CASCADE,
    commit_sha  TEXT   NOT NULL,
    kind        TEXT   NOT NULL CHECK (kind IN (
                    'module','package','file','class','interface',
                    'method','field','source','sink'
                )),
    fqn         TEXT   NOT NULL,          -- com.foo.OrderService.create
    file_path   TEXT,
    start_line  INT,
    end_line    INT,
    signature   TEXT,                     -- JVM 描述符，重载去重靠它
    modifiers   TEXT[] NOT NULL DEFAULT '{}',
    annotations JSONB  NOT NULL DEFAULT '{}',
    extra       JSONB  NOT NULL DEFAULT '{}',
    UNIQUE (repo_id, commit_sha, kind, fqn, signature)
);

-- 代码边
CREATE TABLE IF NOT EXISTS ca_edges (
    id          BIGSERIAL PRIMARY KEY,
    repo_id     BIGINT NOT NULL,
    commit_sha  TEXT   NOT NULL,
    src_id      BIGINT NOT NULL REFERENCES ca_entities(id) ON DELETE CASCADE,
    dst_id      BIGINT NOT NULL REFERENCES ca_entities(id) ON DELETE CASCADE,
    rel         TEXT   NOT NULL CHECK (rel IN (
                    'contains','calls','implements','extends',
                    'has_field','flows_to','guarded_by','references'
                )),
    meta        JSONB  NOT NULL DEFAULT '{}'   -- flows_to 存参数映射
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ca_edges
    ON ca_edges (src_id, rel, dst_id, md5(meta::text));
CREATE INDEX IF NOT EXISTS idx_ca_edges_src ON ca_edges (src_id, rel);
CREATE INDEX IF NOT EXISTS idx_ca_edges_dst ON ca_edges (dst_id, rel);

-- 审计线
CREATE TABLE IF NOT EXISTS ca_lines (
    id          BIGSERIAL PRIMARY KEY,
    repo_id     BIGINT NOT NULL,
    commit_sha  TEXT   NOT NULL,
    source_id   BIGINT REFERENCES ca_entities(id) ON DELETE CASCADE,
    sink_id     BIGINT REFERENCES ca_entities(id) ON DELETE CASCADE,
    sink_line   INT,
    hops        JSONB  NOT NULL DEFAULT '[]',   -- [{entity_id,line,param_map}]
    guards      JSONB  NOT NULL DEFAULT '[]',   -- [{kind,entity_id,detail}]
    reachable   BOOLEAN NOT NULL DEFAULT true,  -- 路由已注册且对外暴露
    candidates  TEXT[] NOT NULL DEFAULT '{}'    -- 由 sink 类型确定性推出
);
CREATE INDEX IF NOT EXISTS idx_ca_lines_repo ON ca_lines (repo_id, commit_sha);
CREATE INDEX IF NOT EXISTS idx_ca_lines_cand ON ca_lines USING GIN (candidates);

-- 审计矩阵（任务看板）
CREATE TABLE IF NOT EXISTS ca_audit_tasks (
    id            BIGSERIAL PRIMARY KEY,
    repo_id       BIGINT NOT NULL,
    commit_sha    TEXT   NOT NULL,
    endpoint_id   BIGINT REFERENCES ca_entities(id) ON DELETE CASCADE,
    vuln_type     TEXT   NOT NULL,
    line_ids      BIGINT[] NOT NULL DEFAULT '{}',
    priority      INT    NOT NULL DEFAULT 0,
    status        TEXT   NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','running','done','skipped','error')),
    verdict       TEXT   CHECK (verdict IN (
                      'confirmed','likely','suspected','clean','needs_review'
                  )),
    confidence    INT    CHECK (confidence BETWEEN 0 AND 100),
    evidence      JSONB,
    intent_id     BIGINT,          -- 关联 exploration_nodes.id（软引用）
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (repo_id, commit_sha, endpoint_id, vuln_type)
);
CREATE INDEX IF NOT EXISTS idx_ca_tasks_status ON ca_audit_tasks (repo_id, status, priority DESC);
```

### 3.2 增量更新设计（必须第一阶段落地）

| 机制 | 做法 |
|---|---|
| 版本标记 | 所有表带 `commit_sha`，结论永远锚定到具体版本 |
| 增量重算 | `git diff --name-only <old> <new>` → 受影响文件 → 重算这些文件的实体/边/线 |
| 跨文件影响 | 被改动方法的**调用方**需要重算（一跳传播，不做全闭包） |
| 失效策略 | 旧 `commit_sha` 的数据保留（历史审计可追溯），新版本全量替换 |
| 幂等 | 导入器按 `(repo_id, commit_sha, ...)` upsert，重复导入无副作用 |

### 3.3 与旧表的关系

- **不改** `assets` / `task_assets` / `task_scope`（渗透模式继续可用）
- **不改** `exploration_nodes` / `exploration_edges`（审计推理链复用）
- **新增** `ca_*` 五张表
- 新增一个 `task_mode` 概念：`pentest` / `codeaudit`，用于前端分流

---

## 4. 代码组织（低冲突二开原则）

### 4.1 目录约定

```
src/
├── codeaudit/                  ← 全新包，不碰上游
│   ├── model/                  实体 / 边 / 线的 Go 结构
│   ├── ingest/                 Joern JSON → DB 导入器
│   ├── rules/                  sink 分类 / guard 抽取 / 一致性规则
│   ├── matrix/                 审计矩阵生成与覆盖度
│   ├── report/                 报告渲染
│   └── cmd/                    CLI 入口（建图、增量、批量审计）
├── db/
│   ├── schema.sql              上游（尽量不动）
│   └── codeaudit.sql           新增，启动时幂等执行
├── agent/
│   ├── planner.go              上游（仅改策略注入点）
│   └── codeaudit_tools.go      新增工具
└── server/
    └── codeaudit_routes.go     新增路由
```

### 4.2 接缝清单（唯一需要改上游文件的地方）

| # | 文件 | 改动 | 侵入度 |
|---|---|---|---|
| 1 | `db/db.go` | 加一行执行 `codeaudit.sql` | 1 行 |
| 2 | `agent/toolcatalog.go` | 注册新 agent key + 工具绑定 | 1 个 map 条目 |
| 3 | `server/server.go` | 挂载 codeaudit 路由 | 1 行 |
| 4 | `agent/planner.go` | 抽出 `IntentStrategy` 接口（矩阵模式 / 探索模式） | ~50 行 |
| 5 | `web/src/app/(main)/layout.tsx` | 加导航入口 / 模式切换 | 少量 |

**原则**：所有新逻辑放新文件；上游文件只做「注册」和「接口抽象」，不改业务逻辑。这样 `git merge upstream/main` 的冲突面控制在 5 个文件内。

### 4.3 提示词改造（零代码）

`agent_prompts` 表已支持运行时覆盖。因此：

- planner 提示词：从「你是渗透规划器」改为「你是审计调度器，消费矩阵，按优先级派发验证意图」
- worker 提示词：增加「代码审计证据规约」（必须引用文件:行号，必须对照兄弟方法）
- 新增 `codeaudit-planner` / `codeaudit-worker` 两个 agent key

这些通过 `promptcatalog.go` 的种子 + 迁移完成，**不改 planner.go 的提示词正文**。

---

## 5. 分阶段实施

### 阶段 0：可行性验证（1 周）

**目的**：证明 Joern 在真实 Java 项目上的数据流质量够用。**这是 Go/No-Go 关卡。**

| 任务 | 产出 |
|---|---|
| 选 2 个真实项目（Spring Boot + MyBatis 单模块；多模块 Maven） | 测试语料 |
| `javasrc2cpg` 建图，导出 JSON | 图规模数据 |
| 手写 3 条查询验证：① SQL sink 可达性 ② `findById` 无归属 ③ `@DataScope` 缺失 | 查询脚本 |
| 评估 Lombok / 反射 / 动态代理 / MyBatis XML 的处理质量 | 质量报告 |

**验收**：至少在一个真实项目上定位到 3 个真实问题（可人工确认）。若失败，重新评估是否改用 CodeQL。

### 阶段 0.5：标注集建设（贯穿，约 1 周人力）

**目的**：建立可度量的基准。

| 内容 | 说明 |
|---|---|
| 来源 | 公开靶场（Java-sec-code 等）+ 内部 2-3 个真实项目 |
| 标注对象 | 越权（水平/垂直）、Mass Assignment、SQL 注入 |
| 规模 | ≥100 个已确认问题 + ≥200 个已确认安全点（用于测误报） |
| 格式 | `{repo, commit, file, line, vuln_type, confirmed_by, note}` |

**没有这一步，后续所有"召回率/误报率"指标都是空话。**

### 阶段 1：图基础设施（2 周）

| 任务 | 文件 |
|---|---|
| DDL + 迁移 | `db/codeaudit.sql`, `db/codeaudit.go` |
| Joern 导出 → 实体/边导入器 | `codeaudit/ingest/` |
| Spring 注解解析（路由、鉴权） | `codeaudit/ingest/spring.go` |
| MyBatis XML 解析（SQL 语句挂载） | `codeaudit/ingest/mybatis.go` |
| 增量更新 | `codeaudit/ingest/incremental.go` |
| 导入 CLI | `codeaudit/cmd/ingest.go` |

**验收**：5 万行项目导入 < 10 分钟；重复导入幂等；增量 < 3 分钟。

### 阶段 2：静态分析规则（2 周）

| 任务 | 说明 |
|---|---|
| sink 分类器 | 按 sink 类型确定性映射候选漏洞类 |
| source 识别 | HTTP param / body / header / principal |
| guard 抽取 | `@PreAuthorize` / `@Secured` / `@DataScope` / `findByIdAndUserId` / 净化函数 |
| 审计线生成 | source → hops → guards → sink |
| 一致性规则 | 兄弟方法守卫签名子集检测 |
| 可达性过滤 | 路由注册 + 对外暴露 |

**验收**：标注集上越权召回 ≥ 60%，误报 ≤ 30%。

### 阶段 3：审计矩阵与覆盖度（1.5 周）

| 任务 | 说明 |
|---|---|
| 矩阵生成 | 端点 × 漏洞类型 |
| 优先级排序 | 可达 + 外部 + sink 严重度 + 污点 |
| 覆盖度统计 | 已审计 / 待审计 / 跳过 |
| 矩阵 API | `GET /api/codeaudit/matrix` 等 |

**验收**：矩阵可视化，空洞可见，优先级排序合理。

### 阶段 4：Agent 接入（2 周）

| 任务 | 说明 |
|---|---|
| 新 agent key + 提示词 | `codeaudit-planner` / `codeaudit-worker` |
| 代码审计工具集 | `read_symbol` / `find_references` / `get_audit_line` / `submit_verdict` |
| 矩阵 → intent 映射 | 一个格子 = 一个 intent |
| 置信度判定 | 四级：confirmed / likely / suspected / needs_review |
| 证据规约 | 强制引用 file:line + 对照方法 |

**验收**：能自动跑完一个项目的矩阵，产出 finding，人工抽检准确率 ≥ 70%。

### 阶段 5：报告与前端（1.5 周）

| 任务 | 说明 |
|---|---|
| 报告模板 | 按漏洞类型分组，含证据链、对照、修复建议 |
| finding 详情页 | 代码路径可视化、跳转源码 |
| 覆盖度看板 | 矩阵热力图 |
| 导出 | HTML / PDF / JSON |

**验收**：报告可交付，人工评审通过。

### 阶段 6：业务逻辑视图（2 周，可选）

| 任务 | 说明 |
|---|---|
| 实体状态机抽取 | status 枚举 + 转移方法 |
| 跨端点状态图 | 同一实体的所有操作端点 |
| 跳步检测 | 转移的前置条件校验 |

**验收**：能发现至少 1 类跳步/状态绕过问题。

### 工期汇总

| 阶段 | 工期 | 累计 |
|---|---|---|
| 0 可行性 | 1 周 | 1 |
| 0.5 标注集 | 1 周（并行） | 1 |
| 1 图基础 | 2 周 | 3 |
| 2 静态规则 | 2 周 | 5 |
| 3 矩阵 | 1.5 周 | 6.5 |
| 4 Agent | 2 周 | 8.5 |
| 5 报告前端 | 1.5 周 | 10 |
| 6 业务逻辑（可选） | 2 周 | 12 |
| 缓冲 | 1 周 | 13 |

---

## 6. 风险登记

| # | 风险 | 影响 | 概率 | 应对 |
|---|---|---|---|---|
| R1 | **Joern 对 Lombok / 反射处理差**，数据流断裂 | 致命 | 中 | 阶段 0 验证；备选 CodeQL（注意商业授权）；Lombok 用 delombok 预处理 |
| R2 | **越权信号弱**，兄弟一致性假设不成立（代码风格不统一） | 高 | 中 | 引入显式策略来源（注解、配置、种子 SQL）作为补充基线 |
| R3 | **LLM 判定幻觉**，把"没看出来"当成"安全" | 高 | 高 | 强制证据规约；`needs_review` 兜底；禁止"确认安全"必须有正向证据 |
| R4 | **成本失控**，大项目 token 爆炸 | 中 | 中 | 三层降本（可达性过滤 / 确定性预筛 / 同 Controller 合并） |
| R5 | **上游合并冲突**，ARTEX 迭代快 | 中 | 中 | 领域层隔离；5 个接缝；提示词走 DB |
| R6 | **标注集不足**，指标失真 | 中 | 高 | 阶段 0.5 优先做；先小后大，持续补充 |
| R7 | **部署依赖 JVM**（Joern） | 中 | 高 | 建图与运行时分离：建图在独立环境/容器，产物是 JSON + DB 数据，生产不依赖 JVM |
| R8 | **代码隐私**，源码出域 | 高 | 低 | 私有化部署；LLM 走内网或脱敏；项目级隔离 |

### 关键风险详解

**R2 是本项目成败的核心。** 如果兄弟一致性假设不成立（例如代码库风格混乱、大量历史遗留），静态越权的召回会大幅下降。缓解手段是把"隐式惯例"和"显式策略"两条线并行：

- 隐式：兄弟方法对比
- 显式：注解、网关配置、`sys_menu` 种子数据、接口文档

两条线互相补位，任一条成立即可产出 finding。

**R3 决定了产品可信度。** 静态审计最怕的不是漏报，是"说安全但其实不安全"。因此：

- `clean` 结论必须附带**正向证据**（"该路径上存在 `@DataScope` + `findByIdAndUserId`"）
- 没有正向证据的，一律 `needs_review`
- 报告中 `clean` 与 `needs_review` 必须分开统计

---

## 7. 成本模型

### 7.1 估算（10 万行 Java 项目）

| 项 | 数量 | 单次 tokens | 小计 |
|---|---|---|---|
| 端点数 | ~800 | — | — |
| 矩阵格子（端点 × 平均 4 类） | ~3200 | — | — |
| 可达性过滤后 | ~1000 | — | — |
| 确定性预筛后 | ~600 | — | — |
| 每格输入（代码上下文） | — | ~10k | 6M |
| 每格输出（判定 + 证据） | — | ~1.5k | 0.9M |
| 重试/补充（×1.5） | — | — | ~10M |
| **合计** | | | **~10M tokens** |

### 7.2 费用

| 模型 | 单价（输入/输出，¥/M） | 单次成本 |
|---|---|---|
| 国产主力（DeepSeek / Qwen） | ~1 / ~2 | **¥15-30** |
| 国产高端 | ~4 / ~12 | ¥60-100 |
| 海外（Claude / GPT） | ~$3 / ~$15 | **$40-80** |

**结论**：国产模型完全可承受；海外模型只能做抽样复核。

### 7.3 三层降本

1. **可达性过滤**：死代码、内部方法、非暴露端点 → 砍 50-70%
2. **确定性预筛**：守卫齐全且无污点的线 → 直接 `clean`，不调 LLM → 再砍 30-40%
3. **同 Controller 合并**：一个端点的多条线合并为一个任务，共享上下文 → 再砍 20-30%

---

## 8. 部署形态

| 组件 | 部署位置 | 说明 |
|---|---|---|
| ARTEX（改造后） | 应用服务器 | Go 单二进制，与原部署一致 |
| PostgreSQL | 同机或独立 | 已有 |
| **Joern + JVM** | **独立建图机 / 容器** | **不进生产运行时**，只产出 JSON |
| LLM | 内网或 API | 支持 OpenAI 兼容协议 |

**关键决策**：建图与分析运行时分离。生产环境只需要「JSON + PG」，不引入 JVM 依赖，避免部署复杂度爆炸。

---

## 9. 与上游的同步策略

| 项 | 做法 |
|---|---|
| 远端 | `git remote add upstream <artex-repo>` |
| 分支 | `main`（我方主线）/ `feature/*` / 定期 `merge upstream/main` |
| 基线 | `695f8a1`（上游 v0.3.15 原样） |
| 冲突控制 | 只允许 5 个接缝文件被修改；其余改动全部在新包内 |
| 差异查看 | `git diff 695f8a1 --stat` 即二开全集 |
| 上游合并节奏 | 每季度一次，或上游有安全修复时 |

---

## 10. 附录

### 10.1 关键代码位置索引

| 用途 | 文件 |
|---|---|
| 探索图 schema | `db/schema.sql`（`exploration_nodes` / `exploration_edges`） |
| 资产 schema | `db/schema.sql`（`assets`） |
| 探索图存储 | `db/exploration.go` |
| Planner | `agent/planner.go` |
| Worker | `agent/worker.go` |
| 工具集 | `agent/tools.go`（2054 行） |
| 工具目录 | `agent/toolcatalog.go` |
| 提示词目录 | `agent/promptcatalog.go` |
| 提示词表 | `db/schema.sql`（`agent_prompts`） |
| 引擎循环 | `server/engine.go` |
| 路由注册 | `server/server.go`（`mux.HandleFunc`） |
| 前端主布局 | `web/src/app/(main)/layout.tsx` |

### 10.2 术语

| 术语 | 定义 |
|---|---|
| **实体（entity）** | 代码图节点：module/package/file/class/method/field/sink/source |
| **审计线（line）** | 从 source 到 sink 的完整数据流路径 + 途经守卫 |
| **守卫（guard）** | 鉴权注解、归属谓词、租户过滤、净化函数 |
| **矩阵（matrix）** | 端点 × 漏洞类型的待办表，一格一个审计任务 |
| **置信度** | confirmed / likely / suspected / needs_review / clean |

### 10.3 待决事项

| # | 事项 | 需谁决策 | 影响 |
|---|---|---|---|
| 1 | 内部工具 or 对外产品 | 业务方 | 是否做多租户 |
| 2 | 是否采购 CodeQL 授权 | 采购 | R1 的备选方案 |
| 3 | LLM 选型（内网部署 or API） | 安全/合规 | 成本与隐私 |
| 4 | 首批试点项目 | 业务方 | 标注集来源 |

---

*文档结束*
