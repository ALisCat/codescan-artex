# 接口 × 漏洞类型 资格矩阵 · 设计说明 v0.1

| 项 | 内容 |
|---|---|
| 版本 | v0.1 |
| 日期 | 2026-11-12 |
| 状态 | 原型已验证（阶段 A） |
| 关联 | `PLAN.md` §2 L2/L3、§5 阶段 2/3 |

---

## 1. 要解决的问题

现有实现（CodeScan-Artex 实测）的工作方式是「**任务驱动接口**」：

```
planner 读代码/文件 → 写一条自由文本意图 → worker 执行
        ↑
   接口只是覆盖度里的一个数字
```

后果（132 接口的真实项目实测）：

| 指标 | 实测值 |
|---|---|
| 接口识别 | 132 / 132（准确） |
| 权限判定 | 132 / 132（准确） |
| **按接口逐条审计的覆盖率** | **23 / 142 ≈ 16%** |
| 能否区分「审过没问题」与「没审」 | **不能** |

本设计改成「**接口驱动任务**」：

```
① 枚举接口（已有）
② 算资格：这个接口能出什么漏洞（确定性）
③ 按优先级派活（一格一任务）
④ 覆盖率 = 矩阵格子状态，空格可见
```

---

## 2. 核心模型：一个格子的三种状态

```
not_applicable   结构上不可能   ← 由 Sink 可达性算出，附不可达证明
applicable       结构上可能     → 派任务
needs_review     结构没命中，但命名/注释提示可疑 → 人工或复核任务
```

**关键**：`not_applicable` 必须可证明，否则和「没审」无法区分。

```
{
  "endpoint": "GET /dept/list",
  "vulnclass": "file-upload",
  "eligibility": "not_applicable",
  "reason": "调用链 3 个方法内未发现 文件上传 所需 Sink，且请求参数不可达",
  "trace": ["DeptController.java:42 getDept", "DeptServiceImpl.java:61 getDept", "DeptMapper.java:12 selectList"]
}
```

> 不做动态验证、不发请求、不编译运行。所有结论只由源码支撑。

---

## 3. 三层信号

### Tier 1 · 资格信号（硬）

只有它能决定 `applicable / not_applicable`，必须确定性、可复核。

| 信号 | 来源 | 例 |
|---|---|---|
| Sink 可达 | 跨文件调用图 | 参数 → `Files.write` |
| Source 类型 | 方法签名 | `MultipartFile` / `@RequestBody` / `HttpServletRequest` |
| 框架语义 | 注解 / MyBatis XML | `${}`、`@Select`、`QueryWrapper.last/apply/orderBy` |
| 依赖存在 | pom.xml | fastjson / shiro / xstream / log4j |

### Tier 2 · 增强信号（软）

**只能提升怀疑，不能下结论，也不能排除。**

| 类别 | 取值 | 作用 |
|---|---|---|
| 路径 | `/upload` `/download` `/export` `/admin` `/proxy` `/callback` | 优先级 |
| 方法名 | `uploadFile` `execCmd` `sendRedirect` `queryByPage` | 优先级 + checklist |
| 参数名 | `url` `filepath` `cmd` `orderBy` `id` `tenantId` | 优先级；`id` 类进 IDOR 候选 |
| 参数位置 | `header` / `cookie` / `path` / `multipart` | checklist 首条 |
| HTTP 方法 | POST / PUT / DELETE | 鉴权类 +2 |
| 返回类型 | `String` + `HttpServletResponse` | XSS 候选 |
| 命名后缀 | `sec` / `safe` / `valid` vs `vuln` / `unsafe` | 改变问法（见 §5） |
| 注释 / Swagger | `@ApiOperation`、`/** ... */` | 优先级 + 问法 |
| 坏味道 | `catch(Exception)`、无 `@Valid`、直接返回实体 | 优先级 |

**非对称规则（必须写进代码）**：

```
结构命中  + 命名可疑  → applicable，优先级 +2/项（上限 +6）
结构未命中 + 命名可疑  → needs_review（不是 not_applicable）
结构未命中 + 命名无感  → not_applicable
命名说安全 + 结构命中  → 仍然 applicable（结构优先）
```

### Tier 3 · 全局信号

不进单格，单独成「全局面」：`permitAll` 白名单、CSRF 关闭、CORS `*`、Actuator 暴露、硬编码密钥、依赖版本。

---

## 4. 安全断言注释（本版新增）

Java 项目里最有价值的注释不是「这段代码做什么」，而是「**这段代码有没有防护**」。

### 词表

```
ASSERT（自述有防护）
  白名单 | 黑名单 | 过滤 | 转义 | 参数化 | 预编译 | 已校验 | 安全处理 | 修复
  safe | secure | whitelist | blacklist | filter | sanitize | validate | escape | fix

NEG（自述有风险）
  未校验 | 未过滤 | 不校验 | 未做 | 存在风险 | 漏洞 | 不安全 | 可绕过 | 绕过
  临时 | 待修复 | TODO | FIXME | vuln | vulnerable | unsafe | bypass

IMPACT（危害关键词）
  任意文件 | 命令执行 | 代码执行 | 注入 | 越权 | 敏感信息 | getshell | rce | ssrf | 反序列化
```

### 生效规则

| 命中 | 效果 |
|---|---|
| 仅 `ASSERT` | 守卫列表追加「注释声明：X」；任务问法转为**「验证能否绕过」**；优先级 −2 |
| 仅 `NEG` | 优先级 +4，标记「注释自述风险」 |
| `ASSERT` + `NEG` | 优先级 +6，标记「注释自相矛盾」（最高价值信号） |
| `NEG` 且结构未命中 | 该格降级为 `needs_review` |

**注释必须与该漏洞类别相关才生效**（用同一套类别关键词过滤），否则一份文件里的 `// vuln code` 会把 8 个类别全部污染。

### 归属窗口

注释按「上一个方法结束 → 本方法结束」绑定，避免上一条方法的 javadoc 串到下一个接口。

---

## 5. 命名后缀决定「问法」

```
/sqli/jdbc/vuln            vs  /sqli/jdbc/sec
/ssrf/urlConnection/vuln   vs  /ssrf/urlConnection/sec
/spel/vuln1                vs  /spel/sec
```

| 变体 | 任务问法 |
|---|---|
| `vuln` / `unsafe` | 「是否存在该漏洞」 |
| `sec` / `safe` / `valid` | 「已有防护（X）能否被绕过」 |

同一个漏洞类型，两种问法，优先级也不同（`sec` 且有守卫 → −3）。

---

## 6. 优先级

```
base     = { command-exec:9, deserialization:9, file-upload:8, sql-injection:7,
             path-traversal:7, ssrf:6, authz:6, xss:3 }[vuln]
exposure = { 公开:3, 登录用户:2, 管理员:1 }[permission]
taint    = { direct:2, indirect:1, none:0 }
guard    = 0 | -3（一个守卫） | -6（两个及以上）

priority = base × exposure + taint×2 + guard
         + min(6, 2 × 命名信号数)
         + 注释信号修正
         + (authz 且路径含 admin/manage/internal/debug ? 6 : 0)
         - (sec 变体 ? 3 : 0)

分档：P0 ≥ 26 / P1 16-25 / P2 < 16
```

---

## 7. 任务生成

**一格一任务，不合并。**

理由：合并会让 LLM 答完最显眼的那一项就收工，而覆盖度是按格统计的。同一接口的多个风险，用 `role` 标记主次：

```json
{
  "matrix_cell": "127:file-upload",
  "asset_ids": [127],
  "endpoint": {"method":"POST","url":"/file/upload","permission":"登录用户",
               "handler":"singleFileUpload","file":"FileUpload.java","line":50},
  "vulnclass": "file-upload",
  "priority": 26, "bucket": "P0",
  "role": "primary",
  "related_cells": ["127:path-traversal"],
  "taint": "direct",
  "variant": "unknown",
  "signals": ["路径","方法名","参数名"],
  "sinks": [{"api":"Files.write","file":"FileUpload.java","line":61,"param":"bytes"}],
  "guards": [],
  "comment_signals": {"assert":[],"neg":[],"impact":[]},
  "summary": "审查 POST /file/upload 的文件上传（权限：登录用户）。参数：file(multipart,MultipartFile) → Files.write @FileUpload.java:61。已发现守卫：无。判定点：①扩展名/Content-Type 白名单 ②文件名净化 ③存储目录不可执行 ④大小限制 ⑤是否可覆盖。只做源码静态分析，结论必须给文件:行号。",
  "prompt_fragment": "file-upload-v1"
}
```

`summary` **由模板生成，不由 LLM 写**——source / sink / guard 都已从图里算出来，planner 不参与派活。

---

## 8. 数据模型

```sql
CREATE TABLE ca_cells (
    id            BIGSERIAL PRIMARY KEY,
    repo_id       BIGINT NOT NULL,
    commit_sha    TEXT   NOT NULL,
    endpoint_id   BIGINT NOT NULL,
    vulnclass     TEXT   NOT NULL,
    eligibility   TEXT   NOT NULL CHECK (eligibility IN ('applicable','not_applicable','needs_review')),
    reason        TEXT,
    trace         JSONB,                -- 不可达证明
    sources       JSONB,
    sinks         JSONB,
    guards        JSONB,
    signals       TEXT[] DEFAULT '{}',  -- 命名/注释信号
    comment_sig   JSONB,                -- {assert,neg,impact}
    variant       TEXT,                 -- vuln | sec | unknown
    taint         TEXT,                 -- direct | indirect | none
    priority      INT  NOT NULL DEFAULT 0,
    role          TEXT,                 -- primary | secondary
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending/running/done/na/review
    verdict       TEXT,                 -- confirmed/likely/clean/needs_review
    confidence    INT,
    evidence      JSONB,
    intent_id     BIGINT,               -- 软引用 exploration_nodes.id
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (repo_id, commit_sha, endpoint_id, vulnclass)
);
```

覆盖度：

```
pct = count(status='done') / count(eligibility='applicable')
na_pct = count(eligibility='not_applicable') / count(*)
未审 = count(status='pending')
```

---

## 9. 实测（java-sec-code，132 接口 / 6.3k 行）

| 指标 | 值 |
|---|---|
| 矩阵规模 | 132 × 8 = 1056 格 |
| applicable | **57（5.4%）** |
| needs_review | 44 |
| not_applicable | 952（90.2%） |
| 任务数 | 60（47 primary + 13 secondary） |
| P0 / P1 / P2 | 14 / 26 / 20 |
| **已知漏洞召回** | **23 / 23 = 100%** |

分类别适用数：

```
文件上传 2 · 路径穿越 5 · SQL 注入 7 · 命令/表达式 14
SSRF 13 · 反序列化 5 · XSS 4 · 越权 10
```

同样的 132 个接口，现有实现只审了 23 个；矩阵做法把 `not_applicable` 的 952 格排除，剩下的 60 格逐个有状态。

---

## 10. 已知局限

| # | 局限 | 影响 | 解法 |
|---|---|---|---|
| L1 | 按方法名做调用图，同名方法会误连 | 误报（已见：`/ssrf/openStream` 误判 path-traversal） | Joern CPG |
| L2 | 特征是正则枚举，写法一变就漏 | 漏报（本语料靠人工补了 `run.exec`/`engine.eval`/`Yaml`/`ExpressRunner` 才到 100%） | Joern + 特征库沉淀 |
| L3 | MyBatis XML 靠名字匹配 | 动态 SQL/`<include>` 会漏 | 自研 XML 解析 |
| L4 | 注释信号依赖中文/英文词表 | 多语言项目失效 | 词表可配置 |
| L5 | 无跨请求业务逻辑 | 状态机/竞态类漏洞不覆盖 | 阶段 6 |

> **100% 召回是在本语料上调出来的，不代表盲测水平。真实项目预估 60-75%。**

---

## 11. 升级路径

### 阶段 A（已完成）
正则 + 方法名 BFS + 命名/注释信号 → 出矩阵 → 人工核对。用于验证数据结构、优先级、任务模板。

### 阶段 B（下一步）
```
Joern javasrc2cpg → CPG
  ├─ 接口枚举：注解查询
  ├─ 参数 → Sink：reachableBy（真污点）
  ├─ 守卫抽取：注解 + 谓词 + 分支
  └─ 自研：Spring 入口解析 + MyBatis XML 绑定
```

验收：

```
标注集 ≥ 50 个已确认漏洞
  资格召回        = 100%
  not_applicable 理由正确率 ≥ 95%
  矩阵规模        落在 150-250 格（132 接口项目）
```

---

## 12. 与现有平台的接缝

| 现有 | 改造 |
|---|---|
| `exploration_nodes(kind=intent)` | 由矩阵格子生成，payload 加 `matrix_cell` |
| planner | 降级为「补漏 / 优先级调整」，不再是任务唯一来源 |
| worker | 复用，提示词按 `prompt_fragment` 注入 |
| coverage | 改为按矩阵统计 |
| assets | 保留，作为矩阵的 `endpoint_id` 来源 |

不改表结构也能先用：把 60 条任务通过 `add_intent(asset_ids=[单值], summary=生成文本)` 投进去即可。

---

## 13. v0.2 修正记录（2026-11-12）

### 13.1 验收结果

用 `acceptance.py` 对 java-sec-code 跑三项硬指标：

| 指标 | 结果 |
|---|---|
| R1 两条已知误报是否消失 | ✅ 都消失 |
| R2 已知漏洞召回 23/23 | ✅ 100% |
| R3 applicable 落在 40-120 | ✅ 57 |

### 13.2 修掉的三类问题

**(1) `new File(x)` 不是文件读取**

```
L1:  new File(`  →  被当成 path-traversal sink
实际： (new File(fullName)).getName()   // 取扩展名
修复： sink 改为真正的读操作 ——
       Files.read*/newInputStream/list/walk、FileInputStream、FileReader、
       RandomAccessFile、getRealPath
结果： /ssrf/openStream × path-traversal 消失
```

**(2) `ImageIO.read(File)` 不是 SSRF**

```
L1:  ImageIO.read(`  →  一律当 SSRF
实际： ImageIO.read(java.io.File) 读本地临时文件；只有重载 (URL) 才是 SSRF
修复： 解析实参标识符的声明类型；类型属于
       File / InputStream / ByteArrayInputStream / MultipartFile → 排除
结果： /file/upload/picture × ssrf 消失
```

**(3) 真实项目上的过度污点（saas-git 暴露）**

```
现象： 35 个接口里 17 个被判 SSRF，实际全是误报
根因： 污点会随「任意实参位置」传给被调方；
       而 URL 来自配置表（changeRelation.getSendUrl() / hospSetting），
       不是请求参数
修复： ① 降污规则：RHS 含 Service/Mapper/Dao/SettingService 调用 → 不传染
       ② SSRF 只使用「字符串型」污点源（对象型参数不传染）
       ③ SSRF 只看「URL 那个实参」（openConnection 看接收者，其余看第 0 参）
结果： 17 → 0（该项目的出网地址全部来自配置，静态上不应判 SSRF）
```

### 13.3 新认识

| 认识 | 说明 |
|---|---|
| `not_applicable` 的可靠性取决于 sink 定义精度 | `new File(` 一类"看起来像"的 API 必须逐个校准，否则误报会以"资格"名义固化 |
| 污点源必须区分「请求」与「配置/DB」 | 这决定了 SSRF、开放重定向的准确率；用统一的"任意参数即源"会系统性过报 |
| 调用图必须带类型 | 两条误报的根因都是"同名/同 API 不同重载"，只有类型能区分 |
| 真实项目的矩阵会"偏科" | saas-git 只有 authz 一格有内容（33/35），因为它的风险集中在鉴权与外部依赖，不在注入 |

### 13.4 Joern 接入受阻（环境问题，非方案问题）

| 通道 | 结果 |
|---|---|
| `github.com` | 不可达 |
| `ghcr.io` 镜像 | 可达但限速 ~100 KB/s，1.5G 镜像约 4 小时 |
| `repo1.maven.org` | 可达，~270 KB/s |
| 本机 JDK | 仅 8；Joern 4.x 需 11/17（yum 可装） |

结论：Joern 仍应作为阶段 B，但应在能稳定访问 GitHub / 有镜像源的机器上做。
本阶段的类型感知改为**本地类型约束 + 调用形态匹配**，已达成同样的验收目标。

---

## 14. Joern 实测（2026-11-12 完成接入）

### 14.1 环境

| 项 | 值 |
|---|---|
| Joern | 4.0.681（`joern-cli-linux-x86_64.zip`，1753 MB） |
| JDK | OpenJDK 17.0.20（与 JDK 8 共存） |
| 安装路径 | `/opt/joern/joern-cli` |
| 建图（java-sec-code，6.3k 行） | **18 秒**，产物 434 KB |
| 导出（156 端点 / 1007 方法） | **14 秒** |

### 14.2 类型证据：两条误报的根因被证实

Joern 能区分同名不同重载，输出 `methodFullName` 自带参数签名：

```
javax.imageio.ImageIO.read:java.awt.image.BufferedImage(java.io.File)
  → FileUpload.java:195        ← 读本地临时文件，不是 SSRF

javax.imageio.ImageIO.read:java.awt.image.BufferedImage(java.net.URL)
  → HttpUtils.java:182         ← 真正的 SSRF
```

这证明了「sink 必须按签名而不是按方法名匹配」这条设计规则。

同理 `new File(x).getName()` 在 CPG 里是 `getName` 调用，不是文件读取；
真正的路径穿越 sink 是 `Files.readAllBytes(Paths.get(...))`。

### 14.3 数据流对比：Joern 精度高，但召回不足

用 `reachableByFlows(handler.parameter)` 对 132 个端点跑真实数据流：

| 指标 | Joern 数据流 | 本设计（规则+启发式） |
|---|---|---|
| 有命中的端点数 | 26 | 46 |
| 已知漏洞召回（23 项） | **8 / 23** | **23 / 23** |

Joern 漏掉的原因（逐条核对）：

| 原因 | 影响的漏洞 |
|---|---|
| MyBatis XML 里的 SQL 不在 Java 数据流里 | 3 个 SQLi |
| 参数先拆成数组再进 `ProcessBuilder` | `/rce/ProcessBuilder` |
| 脚本/表达式引擎的方法模型不全（`GroovyShell`/`ScriptEngine`/`QLExpress`） | 4 个 |
| 通过 `request.getParameter(...)` 再入 sink 的间接流 | `/codeinject` 系列 |
| Spring 文件写入 `Files.write` 的数据流未连通 | `/file/upload` |

### 14.4 结论

> **Joern 不能单独作为资格判定引擎，但它是类型与精度的来源。**

正确的分工：

```
Joern（CPG）        → 端点清单、方法签名、重载消歧、类型
自研规则            → sink 集合、调用形态、跨语言（MyBatis XML）、框架语义
启发式（可降级）    → 拉高召回，标注 needs_review
```

即：**用 Joern 的签名去校准我们的 sink，而不是用 Joern 的数据流替代我们的资格判定。**

### 14.5 落地方式（不重写）

1. 建图与查询离线跑（建图 18s / 查询 14s，可接受）
2. 导出 `endpoints.tsv` / `calls.tsv` / `flows.tsv`
3. 用 `calls.tsv` 的 `methodFullName` 生成**签名级 sink 白名单**，替换现在的正则
4. `flows.tsv` 作为**加分项**（命中即提高置信度），不作为唯一依据

---

## 15. v0.3 重构：矩阵是路由器，不是裁判

### 15.1 职责边界（本节推翻 §2/§7 的部分措辞）

| 层 | 只负责 | 不负责 |
|---|---|---|
| 矩阵 | 派哪些方向、按什么优先级、给什么线索 | confirmed / clean，正报误报 |
| worker | 判定方向是否成立 | 决定覆盖哪些接口 |
| 复核 | 对 finding 做二次判定 | 发现新方向 |

因此矩阵的错误只有两种：

| 错误 | 后果 | 严重性 |
|---|---|---|
| **漏派** | 静默漏报，永远不知道 | 致命 |
| **多派** | worker 花几分钟判 clean | 可接受（成本） |

结论：**资格判定应偏 over-approximation，而不是追求精准。**

### 15.2 任务结构（三段式）

```
【任务】审计 POST /file/upload 的「文件上传」风险

【判定标准】           ← 行业知识，不是代码线索
1. 扩展名 / Content-Type 白名单
2. 文件名净化（../、绝对路径、空字节）
3. 存储目录是否可执行
4. 大小限制
5. 是否可覆盖已有文件

【已知线索（仅供参考，可能不准确或不完整）】   ← 必须带免责
- 入口参数：file(multipart,MultipartFile)
- 代码中出现：Files.write @ FileUpload.java:61
- 已发现守卫：未发现

【要求】
- 独立核实以上线索，不要直接采信
- 除上述线索外，检查该接口是否还有其他同类入口/路径
- 结论只能是 confirmed / clean / needs_more
- confirmed：文件:行号 + 代码片段 + 触发条件
- clean：正向证据（哪一行做了什么校验），无证据不得判 clean
- needs_more：说明缺什么证据
- 只做源码静态分析，不运行、不发请求
```

数据上三者分离：

```json
{
  "direction": "审计 POST /file/upload 的「文件上传」风险",
  "checklist": ["扩展名白名单", "文件名净化", "..."],
  "hints": {"sources": [], "sinks": [], "guards": [], "hint_confidence": "high"},
  "hints_note": "以上线索由静态分析自动生成，可能不准确或不完整",
  "output_contract": {"verdicts": ["confirmed","clean","needs_more"]}
}
```

### 15.3 为什么不能给"结论式线索"

实测依据：CodeScan 的 worker 会严格跟随提示词。

- 意图 #13 写"读 SQLI.java / Jdbc.java / UserMapper.xml" → trace 就只读这三个文件
- 意图 #15 写"SSRF.java 的全部映射" → 它就只在 SSRF.java 里动

所以一旦 summary 写成「参数 file → ImageIO.read@195（疑似 SSRF）」，worker 只会去验证那一条，且失败后容易顺着暗示硬圆结论。

**方向必须中性；线索必须标注非穷尽。**

### 15.4 低置信方向也派

原先把"结构未命中但命名/注释可疑"的格子标 `needs_review` 挂起。
v0.3 改为：**以最低优先级派出**（P3），summary 注明"结构层未确认"。

理由：多派的成本是几分钟，漏派的成本是永远不知道。

### 15.5 验收标准（替换旧的三条）

| 指标 | 含义 | 目标 |
|---|---|---|
| **R1 方向召回** | 已知漏洞对应的 (接口,类型) 必须被派出 | 100% |
| **R2 指针有效性** | hints 引用的 file:line 必须存在且确实包含该 API | 100% |
| R3 派发成本 | 任务总数 | ≤ 预算（120） |

R2 是本版新增的硬指标——**线索指错地方比没有线索更糟**。

### 15.6 实测（java-sec-code，132 接口）

```
结构确认(applicable)  58
低置信(needs_review)  45   → 以 P3 派出
不派(not_applicable) 953

派发任务合计 103   P0/P1/P2/P3 = 16/23/19/45

R1 方向召回   23/23 = 100%
R2 指针有效  101/101 = 100%
R3 成本      103 ≤ 120
→ PASS
```

saas-git（35 接口）：派发 45 条（33 结构确认 + 12 低置信），全部集中在越权方向。

---

## 16. 二开落地（2026-11-12 首次跑通）

### 16.1 改了哪些文件

| 文件 | 改动 | 类型 |
|---|---|---|
| `db/codeaudit.sql` | `ca_cells` 表 + 索引 | 新增 |
| `db/codeaudit.go` | Cell/CellStore：导入、取待办、回写、统计 | 新增 |
| `db/db.go` | `//go:embed codeaudit.sql` + 启动时执行（10 行） | 修改 |
| `server/codeaudit.go` | 5 个路由 + seedCellIntents | 新增 |
| `server/server.go` | 注册 5 条路由（5 行） | 修改 |
| `agent/tools.go` | `submit_cell_verdict` 工具 + SetCellVerdict（~70 行） | 修改 |
| `agent/tools_insert.go` | WorkerTools 注册新工具（1 行） | 修改 |
| `agent/worker.go` | 注入回调 + 矩阵格子提示（~20 行） | 修改 |
| `server/task_llm.go` | 把 task_id 绑到回调（~8 行） | 修改 |

**planner.go / worker 主循环 / 探索图 schema：零改动。**

### 16.2 关键设计：矩阵不接管 planner

导入时直接把格子预置成 `exploration_nodes(kind=intent, state=open)`：

```
POST /api/codeaudit/tasks/{id}/import
  → 写 ca_cells（幂等）
  → 每条待办格子 AddIntent(payload, priority, nil, "matrix")
  → ca_cells.intent_id = 新意图 id, status=dispatched
```

planner 的提示词已经规定"已有 open/running 覆盖的方向不再生成"，
因此下一轮规划看到 112 条 open 意图，不会重复联想。

### 16.3 路由

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/codeaudit/tasks/{id}/import` | 导入矩阵 JSON 并生成意图 |
| POST | `/api/codeaudit/tasks/{id}/seed` | 补派剩余待办（limit） |
| GET | `/api/codeaudit/tasks/{id}/cells` | 列出格子（可按 status 过滤） |
| GET | `/api/codeaudit/tasks/{id}/stats` | 覆盖率与分布 |
| POST | `/api/codeaudit/tasks/{id}/verdict` | 手工回写结论（调试用） |

### 16.4 工具

```
submit_cell_verdict(cell_key, verdict, reason, evidence)
  verdict: confirmed | clean | needs_more
  confirmed 必须给 evidence（文件:行号 + 片段）
  clean     必须给 reason（正向证据）
```

worker 的 system prompt 在意图 payload 含 `cell_key` 时自动追加：
「本意图对应矩阵格子 X，收尾前必须调用 submit_cell_verdict」。

### 16.5 首次实测

```
任务 #1（java-sec-code）
导入 103 条 → 生成 103 条意图 → 3 个 worker 并发消费
约 2 分 40 秒后：cell 13:command-exec → confirmed
  evidence: Rce.java:30-31 /rce/runtime/exec + CommandExec(String cmd)
```

覆盖率接口：

```json
{"total":103,"by_status":{"confirmed":1,"dispatched":102},"coverage_pct":0.97}
```

### 16.6 已知缺口（下一轮）

| # | 问题 | 影响 |
|---|---|---|
| ~~G1~~ | ~~`submit_cell_verdict(confirmed)` 不自动创建 finding~~ **已修（18:11）** | 硬守卫：confirmed 前未调用 report_finding → 工具直接拒绝 |
| G2 | 重启后已 dispatched 的格子不会重新派发 | 卡在 dispatched 的格子需人工 seed |
| G3 | 没有前端看板 | 只能走 API/DB |
| G4 | 生成器仍是离线脚本 | 任务创建后不会自动跑 |

---

## 17. v0.5：合并派发 + 失败回填 + 完成判据

### 17.1 问题（task 3 实测）

```
GET /rce/vuln/yarm  Rce.java:110-113  command-exec         critical
GET /rce/vuln/yarm  Rce.java:110-114  unsafe-deserialization critical
```

同一处 `new Yaml().load(content)` 被两个格子各报一条 finding。

同时发现：意图 blocked/exhausted 时格子会永久停在 dispatched；任务完成判据看
frontier 而不是格子，会"覆盖不全却判完成"。

### 17.2 改动

**(1) 同一接口的多个类型合并成 1 个意图**

```
103 格 → 68 个意图（68 个接口，全部格子都并入）
payload: { summary, cell_keys:[...], cases:[{cell_key,vulnclass,checklist,hints}] }
```

矩阵仍是「一格一行」的账本；只是派发时按接口聚合。worker 提示：

```
本意图包含 N 个格子：...
· 每个格子都要单独 submit_cell_verdict
· confirmed 前必须先 report_finding
· 同一处代码只报一条 finding：多个格子指向同一处时只报一次，其余引用同一证据
```

**(2) 意图失败 → 格子回填**

```
blocked / exhausted / stopped：
  cells.status: dispatched → pending（attempts+1）
  attempts >= 3 → failed（last_error 记录原因）
已有结论（confirmed/clean/needs_more）的格子不受影响。
```

**(3) 完成判据改为「格子全部了结」**

goalless 分支里先查 `ca_cells` 未完成数：

```
unfinished > 0  → 先补派（seedCells）；无可派则回收僵尸 dispatched
unfinished = 0  → 才允许把任务置 done
```

### 17.3 实测（task 4）

```
导入 103 格 → 68 个意图
首个三格意图 #307（GET /rce/groovy）：
  18:command-exec        confirmed   ← 1 条 finding
  18:deserialization     clean
  18:xss                 clean
→ 一个意图、三个结论、只报一条 finding（旧版会报 2-3 条）
```

进度（约 8 分钟）：confirmed 4 / clean 2 / dispatched 97，findings 4 条，
无重复（同 evidence 行号段）。

### 17.4 待验证

| 项 | 状态 |
|---|---|
| 合并派发 | ✅ 已验（#307） |
| clean 回写 | ✅ 已验（2 格） |
| 失败回填 | ⏳ 代码已接，等 blocked/exhausted 触发 |
| 完成判据 | ⏳ 等 frontier 抽干 |

---

## 18. 成本控制与 demo 评测（v0.6）

### 18.1 实测成本（task 4）

```
103 格 → 输入 85.0M / 输出 3.61M / 2757 轮
已了结 79 格 → 每格约 1.08M 输入 token
```

成本来源（按影响排序）：

1. `agents.worker.max_turns = 0`（无限）→ 单意图 30-43 轮，上下文涨到 60k+
2. 配额 429 → blocked → 回填 → 重派 → 再 429（68 → 135 个意图）
3. 任务书里的"自行检查同类入口"导致全仓探索

### 18.2 三个开关（已生效）

| 开关 | 值 | 效果 |
|---|---|---|
| `agents.worker.max_turns` | 15 | 单意图最多 15 轮 |
| `settings.matrix_merge_dispatch` | false | 单格派发（评测期） |
| 配额 blocked | 不回填 | 保留 dispatched，等配额恢复重开 |

代码改动：`settleCells` 增加 quota 分支；`seedCellIntents` 读 `matrix_merge_dispatch`。

### 18.3 Demo 评测协议

目录 `codeaudit/demo/`：

| 文件 | 给谁看 |
|---|---|
| `DEMO-SPEC.md` | 实现者（盲写，只有业务需求） |
| `LABELING-GUIDE.md` | 我们（标注规范） |
| `EVAL-PROTOCOL.md` | 我们（流程与指标） |

核心原则：**是按答案出题，不是按规则出题。**

```
业务规格 → 盲写代码 → 我们标注 → 跑矩阵 → 算指标
```

指标：方向召回 ≥90%、误派 ≤35%、确认准确 ≥80%、clean 证据率 100%、
每格 token ≤250k、每格轮次 ≤12。

防过拟合：规则改一轮就换一版 demo，v1 只做回归不参与调参。

---

## 19. 图谱连线与 planner 补派治理（v0.7）

### 19.1 矩阵意图曾是无父节点

`seedCellIntents` 直接调 `ExplorationStore.AddIntent`，绕过了 `add_intent` 工具里
"顶层意图挂到 origin fact" 的逻辑，导致：

```
task 4: 135 个意图，只有 85 条 derived_from 边（矩阵的 68 个全无父边）
```

图上表现为起点与意图同列、无线相连。

修复：

1. `seedCellIntents` 里补 `Link(originFactID, derived_from, intentID)`
2. 历史数据回填（exploration 1/3/4/5 共 291 条边）

验证：`/api/exploration/graph?task=4` 返回 `derived_from=153`，节点 330。

### 19.2 planner 在矩阵任务里会过度补派

task 4 实测：

```
intent 总数 135 = matrix 68 + planner 67
planner 产出：done 7 / exhausted 25 / blocked 35
```

典型元任务（不产生新知识、只烧预算）：

```
#635 汇总落盘 103 格对照表      blocked
#603 矩阵格子全量盘点+缺口补录   exhausted（还产出了 3 条"结论登记"型 finding）
```

### 19.3 治理措施

| 措施 | 实现 |
|---|---|
| 补派额度 | `settings.matrix_planner_extra_limit`（默认 10）；`add_intent` 超限直接拒绝 |
| 提示词 | planner 提示追加「矩阵任务只补漏；禁止汇总/盘点/落盘/对照表」 |
| finding 范围 | worker 提示追加「只报本意图 cell_keys 的独立漏洞；汇总结论用 record_fact」 |

判定矩阵任务：`ca_cells` 里有该 task 的行。非矩阵任务不受影响。

### 19.4 效果预期

task 4 的 67 条 planner 意图里，至少 40 条属于元任务/重复方向。额度 10 可把这些
从 67 压到 ≤10，预计省下 30-40% 的 token。

---

## 20. 矩阵任务里 planner 不运行的问题（v0.8）

### 20.1 现象

worker 在 fact 672 里写回三条线索（登录无爆破防护、无登出/吊销、token 走自定义头），
planner 没有派任何新意图。

### 20.2 原因

矩阵任务由导入直接生成意图，**没有 goal**。planner 的主循环里：

```go
if !HasOpenGoal() {
    // goalless：worker 跑完就 done，永不进入 planner.Plan
    return
}
```

所以 task 5 从头到尾 **planner.Plan 一次都没执行**（日志里没有任何 `[planner] task 5`），
worker 写回的 fact 自然没人消费。

### 20.3 修复

矩阵任务（`ca_cells` 非空）绕过 goalless：

```
格子未全部了结：
  1. 先补派（seedCells；无新格子则回收僵尸 dispatched）
  2. 不 return，继续跑 planner.Plan —— 让它消化 worker 写回的线索
格子全部了结：
  等没有在跑意图后 → 置 done
```

非矩阵任务行为不变。

### 20.4 仍存在的边界

如果线索是在**所有格子跑完之后**才写回的，任务已经 done，planner 本轮不会再看。
如需覆盖，可在收尾前加一轮「最终线索清扫」；当前先不做（成本/复杂度）。

---

## 21. 完整矩阵入库 + 矩阵看板（v0.9）

### 21.1 之前只有"派发清单"

```
磁盘 cells.json  1056 格（含 953 个 not_applicable + reason + trace）
数据库 ca_cells   103 行（只导入了 tasks.json）
```

数据库无法回答"为什么这格不审"，覆盖率分母也只有 103。

### 21.2 导入完整矩阵

`CellInput` 增加 `eligibility / reason / trace`；导入时：

```
applicable / needs_review → status='pending'（可派）
not_applicable            → status='na'（终态，不派，保留 reason+trace）
```

统计口径改为：

```
applicable_total = total - not_applicable
coverage_pct     = (confirmed + clean) / applicable_total
```

结果：

| 任务 | 总格 | 需审 | N/A | 覆盖率 |
|---|---|---|---|---|
| task 4 | 1056 | 103 | 953 | — |
| task 5 | 96 | 17 | 79 | 94.1% |

### 21.3 矩阵看板

任务详情新增「矩阵」Tab（`_tabs/matrix-tab.tsx`）：

```
行 = 接口（method + url），按最高优先级排序
列 = 8 类漏洞
格 = 状态色块
  灰(虚线) = 不适用     蓝 = 待派      黄 = 已派
  绿 = clean            红 = confirmed  紫 = needs_more   深红 = failed
点格 → 详情：方向 / 判定标准 / 线索 / 结论 / 证据 / 不可达 trace
顶部：矩阵格数 / 需审 / 已了结 / 确认漏洞 / 不适用
```

接口：`GET /api/codeaudit/tasks/{id}/cells`（已有）+ `/stats`（已扩展）。

数据每 5 秒轮询，与 worker 结论同步。

---

## 22. 大项目适配：确定性、生成报告、未验证状态、矩阵 v2（v1.0）

### 22.1 确定性（已修）

同一项目两次运行，`sinks.param` 会变（`bytes` ↔ `path`）。根因是 `tainted` 是 `set`，
字符串哈希随机导致"取第一个命中参数"不稳定。

修复：文件遍历排序、方法索引按 (file,line) 排序、输出排序、所有影响输出的集合迭代 `sorted()`。

验证：不同 `PYTHONHASHSEED` 下两次运行，`cells.json` / `tasks.json` 字节级一致。

### 22.2 生成报告（新增 report.json）

```
files / lines / endpoints / cells
applicable / needs_review / not_applicable / unverified
tasks / duration_sec / lines_per_sec
```

实测：

| 语料 | 行数 | 耗时 | 行/秒 | 格数 | app | rev | na | unverified |
|---|---|---|---|---|---|---|---|---|
| java-sec-code | 6,430 | 1.16s | 5,540 | 1,056 | 58 | 45 | 739 | 214 |
| saas-git | 40,878 | 9.48s | 4,311 | 280 | 33 | 12 | 15 | 220 |

### 22.3 未验证状态（关键）

原来"没找到 sink"= `not_applicable`，分不清"确实没有"和"没解析到"。

新规则：调用链里存在**相关未解析调用**或**同名方法歧义**时，N/A 降级为 `unverified`：

- 不派单（避免洪水）
- 不冒充安全（可见、可后补审计）
- 统计单独计数

分类计数：mapper/dao/repository 只影响 sql-injection；service/client/util/helper/manager
影响所有类型。

**saas-git 上 280 格有 220 格未验证（79%）** —— 这说明按方法名做的调用图在真实业务代码上
分辨率不够，是上 Joern 的直接依据。

### 22.4 矩阵 v2（大项目视图）

- 默认「只看有内容」：隐藏整行都是 N/A/未验证的接口
- 视图切换：接口级 / 前缀聚合（`/api/appointment` 这种模块）
- 搜索接口/前缀
- 聚合格点开 → 下钻到该前缀的接口级
- 新增「未验证」色（浅灰虚线）

规模建议：

```
< 300 行接口：接口级视图
300-1000：默认前缀聚合
> 1000：前缀聚合 + 搜索/筛选（虚拟滚动待做）
```

---

## 23. 修正「未验证」洪水（v1.1）

### 23.1 现象

矩阵里大量格子显示 `?`（未验证）：task 6 的 280 格里 220 个（79%）都是。

### 23.2 原因

旧规则：只要调用链里出现**任意**未解析的 service/domain 调用，就把该接口的**所有**漏洞类型
都降级为 `unverified`。

```
/api/reservation/dept/getDept
  file-upload   → unverified   （但接口根本没有文件参数）
  path-traversal→ unverified
  ssrf          → unverified
  ...
```

等于用"链路不完整"否定了所有类型，信息量为零。

### 23.3 修正

降级前先判断**该类漏洞的 source 前提**是否成立：

| 类型 | 前提 |
|---|---|
| file-upload | 有 multipart 参数，或参数名含 file/upload/attach |
| path-traversal | 参数名含 path/file/name/dir |
| ssrf | 参数名含 url/uri/host/domain/callback/redirect/webhook |
| deserialization | 有 body 参数 |
| sql-injection / command-exec / xss | 命名/注释/路径信号命中 |

没有前提 → 直接 `not_applicable`（"没有入口"本身就是有效论证，不依赖链路完整性）。

### 23.4 效果

| 语料 | 修正前 unverified | 修正后 |
|---|---|---|
| java-sec-code | 214 / 1056 (20%) | **2 / 1056 (0.2%)** |
| saas-git | 220 / 280 (79%) | **34 / 280 (12%)** |

task 6 已就地纠正：`na=201 / unverified=34 / dispatched=36 / confirmed=9`。

### 23.5 展示

- 未验证字形改为 `∅`（needs_more 仍是 `?`）
- **默认隐藏未验证**，勾选「显示未验证」才渲染
- 未验证仍计入统计卡，作为"解析质量"指标

---

## 24. 分析层补齐（v1.2）

v1.0/v1.1 被批评"规则太粗"。根因不是设计错，而是**阶段 A 只实现了编排层，
分析层还是原型**：调用图按方法名 BFS，source 按参数名猜，sink 按方法名匹配。
v1.2 把这三件事都换掉了（仍然不用 Joern）。

### 24.1 接收者类型解析（替代"按方法名瞎猜"）

旧：`deptService.getDept(dto)` → 在全局方法表里找所有叫 `getDept` 的定义，取前 3 个。
后果：同名方法互相污染，链路里混进无关方法的 sink。

新：
1. 解析类索引：`类 → 方法 / 字段 / 父类 / implements`
2. 推断接收者静态类型（形参 → 局部变量 → 字段）
3. 用 `类型.方法` 精确解析；接口走 `implements` 映射到实现类
4. 只有"唯一同名方法"才允许回退；多个同名时记为歧义，不瞎猜

```
deptService (字段: DeptService)
  → impls: DeptServiceImpl
  → DeptServiceImpl.getDept   ✅ 精确命中
```

### 24.2 类型化 source

| 类型 | source 前提（看类型，不只看名字） |
|---|---|
| 文件上传 | `MultipartFile` / `Part` / multipart 参数 |
| 路径穿越 | `File`/`Path`，或 `String` + path/file/name 命名 |
| SSRF | `URL`/`URI`，或 `String` + url/host/callback 命名 |
| 反序列化 | `byte[]`/`Object`，或 body + 显式反序列化信号 |
| SQL 注入 | 字符串来源或 body，**且**全程访问数据层 |
| 命令执行 | `String` + cmd/exec/expression 命名 |
| XSS | `HttpServletResponse` 或显式输出信号（JSON 返回不算） |

### 24.3 签名级 sink

同名不同重载不再混为一谈：

```
ImageIO.read(URL)  → SSRF
ImageIO.read(File) → 不是 SSRF（可作路径穿越的读点）
Files.write(Path)  → 文件写
```

未验证的降级条件也收紧了：只有**带着污点实参**的未解析调用才计入
（常量实参的调用与污点无关，不再制造 `unverified`）。

### 24.4 线索精确到"可以直接跳过去看"

任务书新增：

- body DTO 展开成字段级来源（`getDeptDTO.tenantId`、`getDeptDTO.branchId`）
- 守卫精确到 `file:line`
- sink 记录**实参类型**和**从入口到 sink 的路径**
- 越权格子额外给：数据访问点、当前用户取值点、疑似归属谓词、资源标识参数

worker 不再需要自己 BFS，照着行号核对即可。

### 24.5 低置信格子默认不派

`needs_review` 仍然写进矩阵（可见），但**默认不派单**：

- 派单条件：≥2 个独立信号，或注释自述风险
- 单信号格子留在矩阵里，标 `?`，需要时用 `--low` 强制派

平台侧新增 `status=hold`：

- 不进入 `PendingGroups`（不消耗 worker/LLM）
- 不计入 `applicable_total`（不影响覆盖率，也不阻塞任务完成判据）
- 统计单独计数（`stats.hold`），UI 标「低置信（未派）」
- 默认与「未验证」一起折叠，勾选「显示未验证」可见

### 24.6 指标对比

| 指标 | v1.1 | v1.2 |
|---|---|---|
| java-sec-code 方向召回 | 23/23 | **23/23** |
| java-sec-code 派单 | 103 | **77** (-25%) |
| java-sec-code 未验证 | 2 | **2** |
| saas-git 派单 | 45 | **36** (-20%) |
| saas-git 未验证 | 34 | **29** |
| saas-git 低置信未派 | 0 | **9** |
| 任务书平均字数 | ~830 | 586 (java) / 1654 (saas) |

任务书变长 300~800 字（约 0.2k token），但省掉 2~4 轮盲目探索（每轮 2~6k token），
**净省 token**；同时派单数下降 20%~25%。

生成耗时：java 1.2s，saas 33.7s（要真正跟调用链，比 v1.1 的 9.5s 慢，
但这是一次性成本，且仍在 1.2k 行/秒）。

### 24.7 仍然粗的地方（下一版）

1. **字段级污点**：`this.xxx = param` 再读出会断链（当前只看局部变量/形参）
2. **动态代理 / 多实现**：`implements` 有多个实现时只取排序前 3 个
3. **guard 无语义**：只给位置，是否"真正拦住"仍由 worker 判
4. **反序列化 / XSS 的 source 前提**仍是启发式

这四条才是 Joern（CPG + 真实调用图 + 类型消歧）要解决的。

### 24.8 落地

- 生成器与验收脚本已入库：`codeaudit/tools/{cellgen,acceptance,mkfull}.py`
- 平台已支持 `hold` 状态（DB / stats / UI 全链路）
- task 7（saas-git v1.2）已导入并 seed 完成，未启动：
  `total=280 / applicable=36 / unverified=29 / hold=9 / na=206`
- 与 task 6 对比（同一语料、同一 profile）：派单 45 → 36，低置信 9 个不再消耗 LLM

**关于 token**：平台传给 worker 的是 `cases[].hints` 的结构化 JSON
（平均约 1.8k token/意图），比 v1.1 只给一句方向多了上下文；
但省掉 2~4 轮盲目探索（每轮 2~6k token），并按 20% 比例减少派单，整体是净省。

---

## 25. 用 demo 验证规则（v1.3）

### 25.1 为什么要 demo

真实业务语料不知道"到底有没有漏洞"，只能看方向像不像，**算不出召回和误派**。
v1.3 改用带 ground truth 的 demo（`demo/v1` 安全版 + `demo/v2` 5 处变异版）
直接量化规则。

### 25.2 第一次量化暴露的问题

| 版本 | 真漏洞 | 派单 | 误派 |
|---|---|---|---|
| v1（安全） | 1 | 17 | **94%** |
| v2（变异） | 9 | 16 | **44%** |

结论：**召回高是假象**。v2 的 9 个方向能全派，是因为 v1 把同样的方向也全派了——
规则只看"能否到达 sink"，不看"有没有守卫"。

### 25.3 守卫感知的 hold

`eligibility` 新增 `hold`：写进矩阵、可见，但不派单（平台 `status=hold`）。

只在**结构性守卫**上 hold：

| 类型 | 可 hold 的结构性证据 |
|---|---|
| authz | 归属校验（checkOwner / resource.owner == principal） |
| path-traversal | startsWith / canonical / cleanPath + .. |
| sql-injection | 参数化 / 排序字段白名单 |
| file-upload | UUID 重命名 + 净化 |
| ssrf / command / deser | **只在 sec/safe 变体上 hold**（白名单可能被绕过） |

### 25.4 修复后

| 版本 | 派单 | 召回 | 误派 |
|---|---|---|---|
| v1 | 17 → **1** | 1/1 | 94% → **0%** |
| v2 | 16 → **9** | 9/9 | 44% → **0%** |
| java-sec-code | 77 → **74** | 23/23 | hold 3（全为 sec 变体） |
| saas-git | 36 → 36 | — | hold 0（tenantId 来自请求体，本就该审） |

详细记录见 `demo/RESULTS.md`。

### 25.5 边界

- v2 是 v1 的机械变异，不是独立盲写；仍有过拟合风险。
- hold ≠ 安全，只是"先不烧 token"；错误归属校验会被漏掉。
- 下一步：按同一份 spec 盲写 v3，只跑不调，作为 holdout。

---

## 26. 矩阵看板 v3（可读性 + 窗口化）

### 26.1 问题

v2 的格子是符号（`!` `?` `∅`），用户看不出"这个接口哪些类型会派发、哪些有守卫"；
点开详情还要滚到页面最底部，长矩阵滚动很痛苦。

### 26.2 单元格直接写人话

| 状态 | 单元格文案 | 含义 |
|---|---|---|
| pending | **会派** | 结构可达且无已知守卫，已进 worker 队列 |
| dispatched | **已派** | worker 正在审 |
| confirmed | **漏洞** | 已确认并登记 finding |
| clean | **通过** | 有正向证据，排除 |
| needs_more | **待定** | 缺证据/需外部确认 |
| hold（守卫） | **守卫** | 有归属/参数化/路径限制，保留可见但不派 |
| hold（低置信） | **低信** | 命名/注释信号不足，默认不派单 |
| unverified | **未验** | 调用链没解析全，无法确认 |
| failed | **失败** | 重试耗尽 |
| na | · | 不适用 |

### 26.3 两级详情，不再往下滚

- 点**接口名** → 右侧抽屉：该接口 8 类逐行列出（状态 + 原因 + 优先级），
  点任意一行在抽屉内展开该格详情。
- 点**格子** → 右侧抽屉：方向 / 判定依据 / 结论 / 证据 / 线索 / trace。
- 每行末尾有汇总：`漏洞1 会派3 守卫2 未验1`，一眼看出本行的重点。

### 26.4 窗口化渲染

- 固定行高 34px，只渲染可视区 ±8 行；
- 上/下用 spacer 撑开总高度，`sticky` 表头 + `sticky` 首列仍然可用；
- 1056 格（132 行）实测渲染节点从 132 行降到 ~30 行。

### 26.5 筛选

`全部（有内容） / 只看会派发 / 只看有守卫 / 只看确认漏洞 / 只看未验证 / 只看有结论`，
配合搜索与前缀聚合；默认隐藏"整行都不适用"的接口。

### 26.6 统计卡

矩阵格数 / 会派发 / 已派发 / 未派（守卫+低置信）/ 未验证 / 确认漏洞 / 已排除 / 不适用。

---

## 27. 人工介入：强制发起单格审计（v1.4）

### 27.1 场景

矩阵判定某个接口"不适用 SQLi"，但人工从业务/代码直觉认为可疑时，
需要一种**不修改规则、也不重跑整个矩阵**的方式，让 worker 单独审这一格。

### 27.2 交互

格子详情抽屉（右侧）底部新增「人工介入 · 发起审计」：

- 多行输入框：填写审计建议（≤2000 字）
- 「发起审计」按钮
- 成功后提示 intent id；任务暂停时提示"恢复后执行"
- 已在审计队列中的格子禁止重复发起
- 对已 confirmed/clean/needs_more 的格子重审会覆盖旧结论（UI 有提示）

N/A 格子也可以点开（单元格提示"点击可人工发起审计"）。

### 27.3 后端

```
POST /api/codeaudit/tasks/{id}/cells/audit
{ "cell_key": "/api/auth/login:sql-injection", "suggestion": "重点看 ..." }
```

行为：

1. 校验任务未结束、格子存在且非 `dispatched`；
2. 创建 `origin=manual`、priority=10 的意图，payload 带
   `manual=true` + `suggestion` + 标准 checklist（N/A 格子通常没有 checklist）；
3. 格子 `status=dispatched`、绑定 `intent_id`；
   `eligibility` 为 `not_applicable`/`unverified` 时改为 `applicable`（结论进入覆盖度）；
4. 连同 origin fact 建 `derived_from` 边；
5. 运行中的任务 `Notify()` 唤醒 worker；暂停中的任务只入队。

### 27.4 与自动派发的关系

- 自动派发看 `PendingGroups`（`status=pending`）；人工派发直接把格子置为 dispatched，
  因此不会被 seeder 重复派发。
- worker 仍走 `submit_cell_verdict`，G1 守卫（confirmed 前必须 report_finding）不变。

---

## 28. 漏判扫描：文件资源 authz（v1.5）

### 28.1 扫描方法

`tools/gapscan.py`：从 endpoint 出发做结构可达 BFS，收集**所有 sink 命中**
（不做污点判定），再和 cells.json 的 eligibility 对比。
凡是"代码里有 sink、矩阵却判 N/A"的 (接口,类型) 全部列出来人工复核。

### 28.2 demo-v2 暴露的漏判

`GET /api/file/download` 在 M2 变异后：

- `path-traversal` 判了 applicable（正确）；
- `authz` 判了 **N/A**，原因"未访问数据层"——因为 M2 同时删掉了
  `attachmentMapper.findByFilePath`（DB 查询）和归属校验。

但"任意登录用户按 path 读任意文件"本身就是越权。
根因：**authz 的 `has_da` 只认 DB/缓存，不认文件读写**。

### 28.3 修复

- `has_file_da`：该接口的 `file-upload`/`path-traversal` 格子存在 sink 时，
  视为"访问文件资源"，authz 也进入判定；
- 文件类 authz 的 `da_sites` 用文件 sink 的位置补齐，worker 仍能拿到行号。

### 28.4 回归

| 语料 | 变化 | 验收 |
|---|---|---|
| demo-v1 | 不变：download/upload 的 authz 因归属校验 → hold | 1 派单 / 0 误派 |
| demo-v2 | `file/download:authz` 从 N/A → applicable | 10/10 召回 / 0 误派 |
| java-sec-code | 派单 74 → 79（文件接口的 authz） | R1 23/23 / R2 100% / R3 PASS |
| saas-git | 0 变化（无文件读写接口） | — |

### 28.5 saas-git 的扫描结论

- **没有确认漏判**；
- 29 个 `unverified`：28 个 SQLi + 1 个 XSS，全部是"同名歧义"噪声；
  代码里没有用户可控的 `${}` / `.last()` / `.apply()`；
  唯二的 `${tableName}` mapper（Dictionary/LogInfo）**没有调用点**；
- `file-upload`/`path-traversal`/`command-exec`/`deserialization`：全项目没有对应 sink；
- 2 个 authz N/A：`/api/reservation/admin` 返回常量 "OK1"，
  `/api/reservation/notice` 是 `return false` 的桩。

### 28.6 仍未覆盖的 authz 形态

authz 现在认 DB + 文件资源，但**不认"纯外部副作用"**：
例如一个只调用 HIS 退款、不在本地查库的接口，按订单号退款给任意人。
saas 的退款接口都有本地查库，所以这轮没踩到；规则上仍是洞，需要按项目补。

---

## 29. P0：调用解析消歧（v1.6）

### 29.1 目标

saas 的 29 个未验证里 28 个是 SQLi，全部来自"同名歧义"；
先把**解析噪声**打掉，再谈补 sink / 字段污点。

### 29.2 改了什么

1. **框架/工具方法白名单**
   `getOne/list/save/updateById/page/count/lambdaQuery`（MyBatis-Plus）、
   `findById/findAll/saveAll`（Spring Data）、`getRequest/getResponse/isBlank/isEmpty`（静态导入）、
   `get/put/remove/add/stream/collect`（集合/lambda）——本类/父类找不到时按 **external** 处理，
   不再计入 ambiguous。
2. **构造器不是方法**
   `new BusinessException(...)`、`new InputTreeBuilder(...)` 之前被当成方法调用，现已跳过。
3. **大写接收者 = 静态调用**
   `StringUtils.isBlank`、`RequestHeaderUtil.getRequestHeader`、`CalibrationUtil.xxx`：
   类里没有该方法就按 external，不再回退到全局同名方法。
4. **类型推断补 enhanced-for**
   `for (Map.Entry<K,V> entry : ...)` 里的 `entry` 现在能推断为 `Map.Entry`。
5. **按签名消歧**
   多个同名候选时，先用**实参个数**过滤，再用**首参类型**过滤；唯一命中才采用。
6. **Bean 名匹配**
   接口有多个实现时，按字段名匹配实现类（`deptService` → `DeptServiceImpl`）。
7. **接口无 body → external**
   工程内接口没有实现类、也没有方法体时，视为委托外部，不再记未解析。

### 29.3 顺手修掉的 authz 回归

P0 收紧了调用链，暴露出 `has_da` 的两个问题：

- MyBatis-Plus 的 `this.list(...)` / `this.getOne(...)` 没有点号，旧正则漏判 → 补"无接收者框架方法"；
- `principal` 之前用 `getTenantId` 判断，把 **DTO 里的 tenantId** 也当成登录上下文 →
  改为只认 `RequestHeaderUtil.getRequestHeader` / `UserContext.require` / `SecurityContext` / `LoginUser`；
- 新增：**无 principal + 外部数据调用（HIS/HttpRequest/RestTemplate）** → authz applicable，
  覆盖"未登录直接查 HIS"的接口。

### 29.4 指标

| 指标 | v1.5 | v1.6 |
|---|---|---|
| saas 未验证 | 29 | **5（-83%）** |
| saas 歧义计数 | 671 | **4** |
| saas applicable | 33 | 33 |
| saas 派单 | 36 | 36 |
| demo-v1 未验证 | 8 | **0** |
| demo-v2 未验证 | 7 | **0** |
| demo-v1 召回 / 误派 | 1/1 / 0 | 1/1 / 0 |
| demo-v2 召回 / 误派 | 10/10 / 0 | 10/10 / 0 |
| java 未验证 | 2 | **0** |
| java 验收 | R1 23/23 | **R1 23/23 / R2 100% / R3 81** |

### 29.5 剩下的 5 个未验证

```
/api/reservation/noticeV3                      sql-injection  1 unresolved + 1 ambiguous
/api/reservation/register/notifyCallBack       sql-injection  1 unresolved
/api/reservation/register/registerCancel       sql-injection  1 ambiguous
/api/reservation/register/registerCheckInList  sql-injection  1 ambiguous
/api/reservation/register/zeroLockNum          sql-injection  1 unresolved + 1 ambiguous
```

这 5 个是真的"链没解析全"，建议用人工介入各跑一格确认；
如果确认无 SQLi，再决定是否继续做 P1/P2。

---

## 30. 矩阵工程化：图 → 分析器 → worker（v2.0 方向）

### 30.1 三层职责

| 层 | 只做 | 不做 |
|---|---|---|
| **图** | 接口完整流程：controller → service → impl → dao；方法 span、调用边、字段/参数、SQL 位置、未解析标记 | 不判断漏洞 |
| **分析器** | 沿图的 flow 回到源码，找该类的 **sink** → possible / impossible / unknown | 不做污点、可达性、白名单、防护判断 |
| **worker** | 判断参数是否可达、是否有参数化/白名单/归属校验、是否可利用 | 不需要全量审 8 类 |

### 30.2 状态机

```
possible    流程里找到该类 sink        → 派发
impossible  流程里完全没有该类 sink   → 不派
unknown     图不完整，可能藏着 sink   → 最低优先级 / 可选
```

不再有"有守卫 → hold 不派"。守卫只作为 `guards_seen` 证据交给 worker。

### 30.3 分析器协议

```python
class Analyzer:
    vulnclass: str
    def analyze(self, endpoint, flow, ctx) -> list[Finding]:
        # ctx.read(file, start, end) / ctx.sql_of(dao, method)
        ...
```

Finding：

```json
{
  "vulnclass": "sql-injection",
  "state": "possible",
  "sink": {"file": "...", "line": 77, "api": "deptMapper.selectList"},
  "evidence": {"sql": "...", "source_params": ["tenantId"]},
  "guards_seen": ["#{}"],
  "missing": null
}
```

### 30.4 分析器按类型

| 类型 | 分析器只找 |
|---|---|
| 命令注入 | `Runtime/ProcessBuilder/ScriptEngine/SpEL/Groovy/QLExpress/...` |
| SQL 注入 | DAO 调用 / JDBC 执行 / wrapper 构造（不区分 `#{}` 与 `${}`） |
| 越权 | 资源访问（DB/文件/外部）+ 接口资源标识参数 |
| SSRF | 出站 HTTP 调用 |
| 文件上传/路径穿越 | 文件读写 API |
| 反序列化 | `ObjectInputStream/readObject/XStream/...` |
| XSS | 响应写出 API |

### 30.5 worker 任务书

```
接口：POST /api/...
流程：
  1. Controller.method @ file:line
  2. ServiceImpl.method @ file:line
  3. Dao.method @ file:line（SQL/wrapper）

候选类型：possible 的 N 类

请判断：可达性、参数可控、白名单/防护、归属校验
结论：confirmed / clean（正向证据）/ needs_more
```

### 30.6 落地阶段

1. **Phase 1**：JavaParser + Spring + XML 导出 `graph.json`（含 span）。
2. **Phase 2**：先实现命令注入、SQL 注入、越权三个分析器；其余用 legacy adapter。
3. **Phase 3**：绑定矩阵 + worker 任务书，demo/java/saas 逐格对比。
4. **Phase 4**：替换 monolith，`cellgen.py` 只保留 CLI。

### 30.7 成本控制

候选会变多（方向优先）。只允许用以下方式降成本，不允许用守卫排除方向：

- 优先级排序（sink 离入口近、参数直接进 sink 的排前）；
- 同接口合并派发；
- 按类型设置 max_turns；
- 任务书直接给守卫代码，减少 worker 探索。

---

## 31. v2 流水线落地（M0–M5）

### 31.1 已落地

```
tools/callgraph/                 JavaParser sidecar（classes/fields/methods/calls/spans）
matrix/graph/build.py            JavaParser + Spring + XML → graph.json
matrix/context.py                图 + 按 file:line 读源码
matrix/analyzers/*.py            8 类分析器：authz / sql / command / ssrf /
                                 file / path / deser / xss
matrix/catalogs/*.yaml           sink / guard / input 目录
matrix/run.py                    跑分析器 → findings.json
matrix/bind.py                   findings → cells/tasks/report
matrix/mkimport.py               binder 输出 → 平台导入体
```

状态机：`possible / unknown / impossible`。

- possible → 派发；
- unknown → 平台映射为 `unverified`，不派；
- impossible → `not_applicable`。
- **不再有"守卫 → hold"**；`guards_seen` 只进 hints。

### 31.2 度量

| 语料 | cells | possible | unknown | impossible | tasks |
|---|---|---|---|---|---|
| demo-v2 | 96 | 28 | 0 | 68 | 28 |
| demo-v1 | 96 | 29 | 37 | 30 | 29 |
| saas | 280 | 91 | 29 | 160 | 91 |
| java-sec-code | 1056 | 96 | 22 | 938 | 96 |

- demo-v2 种下的 10 个漏洞全部 possible；
- java-sec-code 23 个已知漏洞全部 possible，acceptance R1 23/23、R3 96；
- demo-v1 的安全代码也产生 29 个方向（方向优先，worker 判定）。

### 31.3 平台验证

task 9（demo-v2，v2 流水线）：

```
96 cells = 28 applicable + 68 na
seeded=28，intent payload 带 flow/sites/guards_seen
```

UI 已支持：

- 「未知/未验证」文案；
- 格子详情展示结构流程、sink/资源访问、守卫线索；
- 原始 hints 折叠。

### 31.4 未完成

- M6 worker A/B（有/无结构流程对比文件操作/轮次）；
- unknown 的独立 DB 状态（当前复用 `unverified`）；
- 旧任务 `hold` 数据迁移；
- 分析器单测 / fixture；
- 优先级细化（公开接口、直接参数）。

### 31.5 第一次 A/B（同一份 demo-v2，同一格）

| 格子 | 流水线 | 意图 | 文件操作 | steps | output token | 结论 |
|---|---|---|---|---|---|---|
| `/api/appointment/{id}:authz` | 旧（sinks/da_sites） | 799 | 62 | 113 | 117,701 | confirmed |
| `/api/appointment/{id}:authz` | 新（flow/sites/guards） | 813 | 70 | 120 | 108,746 | confirmed |
| `/api/notice/send:authz` | 旧 | 800 | 60 | 132 | 109,113 | confirmed |
| `/api/notice/send:authz` | 新 | 811 | 76 | 127 | 97,539 | confirmed |

结论：

- **结论没有退化**：两格都是 confirmed，finding 也都登记了；
- **output token 降 7.6% / 10.6%**；
- **文件操作没有降，反而 +13% / +27%**；
- 两个旧意图都打满 15 轮，新意图也打满 15 轮；
- 旧任务期间出现 429（12 次），新任务没有。

说明：**只给结构 flow 不足以让 worker 少探索**。下一步必须配合：

1. 在 intent 顶部给一段紧凑的 `audit_path` 文本（而不是埋在 JSON 里）；
2. prompt 硬约束："先按 flow 核对；找到 sink 和守卫即可提交；flow 不完整才 grep"；
3. authz 的 max_turns 从 15 降到 8；
4. 同接口合并派发。

### 31.6 修复评测污染 + 干净 A/B

**修复：**

1. 评测标注移出源码树：`demo/labels/v1.csv`、`v2.csv`；
2. 新增 `tools/pack_source.py`，打包时排除 `GROUND-TRUTH.csv` / `labels` / 构建产物；
3. 删除 task 8/9 源码目录里的 `GROUND-TRUTH.csv`；
4. worker prompt：
   - 矩阵 intent 前增加紧凑【审计路径】（flow/sites/guards）；
   - 明确"只读列出的文件；最多 Read 8 次 / Grep 3 次；找到 sink+守卫即提交"；
   - 矩阵任务不再使用"发散是好事"的全局提示；
5. `agents.worker.max_turns` 15 → 8。

**干净 A/B（同格，无 GROUND-TRUTH）：**

| 格子 | 流水线 | 文件操作 | reads | greps | steps | output | 结论 |
|---|---|---|---|---|---|---|---|
| appointment/{id}:authz | 新 | 18 | 14 | 4 | 59 | 73,486 | confirmed |
| appointment/{id}:authz | 旧 | 18 | 12 | 6 | 60 | 61,823 | confirmed |
| notice/send:authz | 新 | 8 | 8 | 0 | 47 | 137,263 | confirmed |
| notice/send:authz | 旧 | 34 | 16 | 2 | 72 | 89,467 | confirmed |

truth_reads = 0（四个意图均未读标注）。

结论：

- prompt/overview/max_turns 修复后，文件操作从 60+ 降到 18/34；
- audit_path 对 notice 格进一步降到 8（-76%），appointment 持平；
- 两格都 confirmed，结论没有退化；
- output token 没有下降（新 73k/137k vs 旧 62k/89k），需要继续观察。

### 31.7 验证：worker 是否按审计路径走

修复 `hints_note` 冲突（payload 里硬编码的"检查其他同类入口"）后，跑 task 10 的
`/api/appointment/list:authz`（intent 861）单意图验证。

结果：

```
state=exhausted（max_turns 已恢复 15）
file_ops=16  reads=14  greps=0  steps=71  out=76,847
读过的文件（7 个，全部在 flow/principal 上下文内）：
  AppointmentController.java
  AppointmentService.java
  UserContext.java
  LoginUser.java
  ApiResponse.java
  AppointmentMapper.xml
  AppointmentMapper.java
结论：clean（正确：role 校验 + patientId 查询）
```

对比修复前：

```
文件操作 60~76 → 16
distinct 文件 25（含所有 controller/service、README、GROUND-TRUTH）→ 7
grep 0
```

说明：

- 结构流程/sink/守卫确实发给了 worker；
- 去掉冲突文案后，worker 会按路径读文件，不再全项目扫；
- max_turns 15 仍会打满、output token 仍高，成本优化暂时不做（按用户要求先保流程）。

### 31.8 helper 调用是否进图（checkOwner）

问题：图给出接口流程，但 impl 里可能调用 `checkOwner` 这类 helper；worker 会不会读？

修复：`graph/build.py` 的 `fallback_call` 在**无接收者**时按"当前类 + 父类"回退。
之前 self 调用用 FQN 去查 cellgen 的 simple-name 索引，导致 `checkOwner` 落到 unresolved。

验证（demo-v1 `/api/appointment/{id}:authz`，task 12 / intent 926）：

```
flow: detail → ok → detail → findDetail[dao] → require → checkOwner @ AppointmentService.java:129
file_ops=22  reads=14  greps=6  steps=75  out=239,644
distinct files=7（全部在 flow/principal 内）
verdict=clean
evidence 明确引用：checkOwner(detail.getPatientId(), user);
```

结论：

- helper 在**已解析调用链**上时会进 flow，worker 会读；
- 同文件 helper（如 checkOwner）已被覆盖；
- 跨文件/未解析的守卫 helper 落地在 `unresolved`，prompt 增加窄例外：
  "看到 checkOwner/checkPermission/hasRole 等守卫调用且实现不在 flow 时，允许读该守卫函数"。

副作用：saas 图覆盖提升（有 DAO 的端点 30 → 33，authz possible 32 → 33）。

---

## 32. 已知缺口：planner 新意图绕过矩阵格式

### 32.1 机制

矩阵意图的 payload：

```json
{"cell_keys": ["/api/...:authz"], "cases": [{"cell_key": "...", "hints": {"flow": [...], "sites": [...], "guards_seen": [...]}}]}
```

- `renderIntentTask` → `matrixIntentPrelude` 能生成【审计路径】；
- `renderWorkerGraphOverview(..., true)` → 使用严格版 overview；
- 有"只读列出的文件 + 守卫 helper 例外"的硬约束。

planner 通过 `add_intent` 生成的意图：

```json
{"summary": "审计全局鉴权机制本身：interceptor/AuthInterceptor.java ...", "asset_ids": []}
```

- 没有 `cell_keys` / `cases`；
- `matrixIntentPrelude` 返回空；
- `intentCellKeys` 返回 nil → overview 走**非矩阵**分支（含"发散是好事"）；
- 没有审计路径、没有读预算、没有停止条件。

### 32.2 证据（task 10）

```
planner 意图 6 个：896/897/898/899/913/914
matrix 意图 28 个
```

planner 意图的 summary 是全局/跨接口任务，例如：

- 审计全局鉴权机制（AuthInterceptor / WebMvcConfig / application.yml）
- 审计凭据与口令安全（PasswordConfig / AuthService）
- 枚举全部 HTTP 端点，与矩阵做差集
- 预约业务的状态机/并发/重复退款

这些意图被 worker 领取后，会按非矩阵方式全项目阅读。

### 32.3 影响

- 每个 planner 意图可能重新读全项目，成本高；
- 可能与矩阵格子重复审计；
- 也可能越出矩阵范围（例如凭据哈希、异常泄露），这些是有效方向，但缺少范围约束。

### 32.4 候选完善方向（未实现）

1. **add_intent 时做图富化**：payload 增加 `targets`（endpoint/vulnclass/file），服务端查 graph，自动补 `cases[].hints`；
2. **planner 只产出"候选格"**：planner 通过一个矩阵候选工具写 cell，再由 binder 富化并派发，不直接生成裸意图；
3. **渲染器兜底**：无 `cases` 时，从 summary 里提取 `*.java` / `/api/...`，生成"目标文件/接口"范围；
4. **给所有意图加读预算**：全局意图给更大预算，但仍有上限；
5. **意图分类**：`global` vs `endpoint`，只有 global 使用发散版 overview。

### 32.5 当前结论

先记录，不在本轮修改。矩阵本身闭环已通；planner 补漏意图是下一步要收口的成本/范围问题。

---

## 33. 待做：guard_helpers（跨文件 / 未解析守卫）

### 33.1 背景

- 同文件 helper（如 `checkOwner`）已经能进 flow，worker 会读（见 31.8）；
- 跨文件 helper 如果被解析，BFS 会进 flow；
- 跨文件 helper 如果 unresolved，只落在 `unresolved`，worker 只有 prompt 的窄例外，**没有明确 file:line**，仍可能漏。

### 33.2 设计

新增 `hints.guard_helpers`：

```json
[
  {"name": "checkOwner", "kind": "ownership",
   "file": "AppointmentService.java", "line": 46,
   "resolved": true,
   "target_file": "PermissionService.java", "target_line": 88,
   "target_end": 96},
  {"name": "hasRole", "kind": "role",
   "file": "AuthInterceptor.java", "line": 54,
   "resolved": false,
   "target_file": "", "target_line": 0}
]
```

生成方式：

1. 扫描 flow 中每个方法体，匹配守卫调用名：
   `checkOwner|checkOwnership|checkPermission|verifyOwner|assertOwner|isOwner|belongs|hasRole|hasPermission|checkAuth`
2. 尝试解析目标：
   - 当前类 / 父类 / 接口实现；
   - 字段类型 + bean 名；
   - JavaParser 解析结果 + 现有 fallback。
3. 解析成功 → `resolved=true` + `target_file/line/end`；
4. 解析失败 → `resolved=false` + 调用点 `file:line`。

### 33.3 渲染

- `matrixIntentPrelude` 优先打印 `guard_helpers`，即使它在 flow 第 12 步之后；
- prompt：
  - resolved：允许读 `target_file` 的 `target_line` 段；
  - unresolved：允许按名字/调用点查找，但仍限制在守卫实现，不扩展到其他接口。

### 33.4 验收

1. demo-v1 `checkOwner` 出现在 `guard_helpers`，带 `target_file/line`；
2. 构造一个跨文件 helper fixture（v3）：service 调 `OwnershipChecker.check(...)`，worker 能读到 helper 并给出 clean/confirmed 证据；
3. saas 统计 resolved/unresolved 数量；
4. 不增加 `impossible` 误杀。

### 33.5 优先级

- 先完成流程稳定性（worker 按 flow 走、planner 意图收口）；
- 再做 `guard_helpers`；
- 最后做硬性读预算 / token 优化。

### 32.6 已实现：planner 意图范围兜底（本轮）

实现（`agent/worker.go`）：

1. `plannerIntentPrelude`：无 `cases/cell_keys` 时，从 `summary` 提取
   `*.java/*.xml/*.yml/*.properties` 和 `/api/...`，生成【planner 补漏范围】；
2. `renderIntentTask`：矩阵 prelude 为空时回退到 planner prelude；
3. `renderWorkerGraphOverview` 增加 `planner` 模式：
   - 不再使用"发散是好事"；
   - 要求先按范围读、全局任务先列清单、最多读 10 个文件；
4. `/api/...` 正则支持 `**`（`/api/admin/**`）。

验证（task 10，planner intent 896：全局鉴权机制）：

```
state=done（未打满）
file_ops=42  reads=30  greps=2  steps=87  out=62,245
distinct files=15：
  3 个范围文件（AuthInterceptor / WebMvcConfig / application.yml）
  + ClinicProperties
  + 全部 Controller（意图本身要求逐一枚举端点）
  + UserContext / LoginUser / AuthService
未读：README、schema.sql、GROUND-TRUTH、全部 Service
产出：finding 119 high
  "管理面接口缺失角色鉴权：AuthInterceptor.needAdmin() 为零调用死代码…"
```

结论：planner 意图不再全项目扫；会先读范围文件，再按意图需要扩到 Controller。

残留：

- 全局意图可能合理地超过 10 个文件（例如枚举全部端点），需要后续按
  `global` / `endpoint` 分类设预算；
- 更彻底的做法是 `add_intent` 时写入结构化 `targets`，由 planner 自己声明范围。

### 31.9 多类型流程验证（task 13）

语料：demo-v2 干净包（无 GROUND-TRUTH），新流水线 28 possible。

| 类型 | 意图 | state | ops | reads | greps | steps | out | 结论 |
|---|---|---|---|---|---|---|---|---|
| path-traversal | 976 | done | 6 | 6 | 0 | 41 | 34,921 | confirmed |
| sql-injection | 979 | done | 8 | 8 | 0 | 42 | 36,059 | confirmed |
| ssrf | 982 | done | 14 | 10 | 0 | 74 | 121,966 | confirmed |

读过的文件（全部在 flow 内）：

```
path: FileController, FileService, UserContext
sql : ReportController, ReportService, AppointmentMapper.xml, UserContext
ssrf: NoticeController, NoticeService, UserContext, ApiResponse, NoticeSendRequest
```

产出：

- `GET /api/file/download` 路径穿越 → 任意文件读取（FileService.download 未做根目录约束）
- `GET /api/report/appointments` `${}` 拼接 → ORDER BY SQL 注入
- `POST /api/notice/send` webhook 未校验 → SSRF

结论：

- 三类都能按审计路径走完，0 次 Grep，没有全项目扫；
- 三条 finding 都正确、带文件行号；
- 三个意图都是 `done`，没有打满 15 轮；
- SSRF 的 output 121k 偏高，属于 worker 推理量，不是读文件多。

## 34. authz_model v0.1：语义守卫（不按方法名）

### 34.1 动机

旧方案用 `checkOwner|checkPermission|...` 名字在 flow 里找守卫，用户明确指出会漏：

```java
private void ensureAccess(Order order, LoginUser user) { ... }
boolean ok = accessService.canSee(order, user);
```

方法名可以任意起，名字目录无法覆盖。v0.1 改为行为签名：

```
principal 来源 + resource/role 参与条件 + 拒绝路径（throw/403/401/redirect）
```

名字只作为 flow 展示的提示，不再作为判定依据。

### 34.2 实现

`matrix/guards/`：

| 文件 | 职责 |
|---|---|
| `scan.py` | 解析方法签名/变量来源/if 条件/throw/return/sendError；任意命名 helper |
| `policy.py` | HandlerInterceptor / WebMvcConfigurer / SecurityFilterChain / TenantLineHandler / 白名单 |
| `engine.py` | 组装 principal/resource/decisions/required/coverage/gaps/unknowns/guard_helpers |

能力：

- inline 守卫：`if (!order.getOwnerId().equals(user.getId())) throw`；
- 同文件/跨文件 helper：flow 里能解析到的方法体直接扫描；
- 返回值守卫：`if (!canSee(order,user)) throw` → 扫描 `canSee` 的 return 表达式；
- 注解守卫：`@PreAuthorize`/`@Secured`/`@RolesAllowed`/Shiro/Sa-Token；
- 全局策略：认证拦截器、角色路径、白名单、租户插件；
- 死守卫：`needAdmin` 声明了路径但 `preHandle` 未调用 → `required role` + `unknowns`，不记 observed；
- 业务校验（`if (amount < 0) throw`）没有 principal/resource 参与 → 不是守卫。

### 34.3 数据

`authz_model`：

```json
{
  "principal": {"var": "user", "type": "LoginUser", "source": "UserContext.require()", "file": "...", "line": 41},
  "resource": {"var": "order", "type": "Order", "source": "mapper.findById(id)", "file": "...", "line": 42},
  "decisions": [
    {"kind": "authentication", "rule": "principal or interceptor", "file": "...", "line": 34},
    {"kind": "ownership", "rule": "order.ownerId == user.id", "file": "...", "line": 46,
     "target_file": "...", "target_line": 129, "resolved": true},
    {"kind": "role", "rule": "ADMIN", "source": "policy", "file": "...", "line": 54}
  ],
  "required": ["authentication", "ownership"],
  "coverage": ["authentication", "ownership"],
  "gaps": [],
  "unknowns": []
}
```

`guard_helpers` 从 decision 派生：resolved 给 `target_file/target_line/target_end`；
unresolved 给 `call_file/call_line` + 条件，worker 可只读这些实现。

### 34.4 接入

- `analyzers/authz.py`：把 `authz_model` / `guard_helpers` 放进 evidence；
- `bind.py`：authz 任务的 `hints` 带 `authz_model` / `guard_helpers`；
- `worker.go` 的 `matrixIntentPrelude`：authz 格优先打印模型，抑制原始 `guards_seen`；
  `writeAuthzModel` 渲染 principal/resource/decisions/required/coverage/gaps/unknowns/helpers。

### 34.5 验证

demo-v2（labels/v2.csv，authz 11 条）：

| 端点 | 结论 | gaps |
|---|---|---|
| /api/appointment/{id} | vuln | ownership |
| /api/file/download | vuln | ownership |
| /api/notice/send | vuln | role |
| /api/report/appointments | vuln | role |
| /api/admin/config | vuln | role |
| 其余 6 条 safe | safe | 无 |

demo-v1：12 个 authz 格全部无 gap。

改名验收：

```
checkOwner → ensureAccess
```

`authz_model` 的 decisions（ownership + role @130）不变。

fixture `/tmp/opencode/authz-fixture`：

- `ensureAccess`（任意命名）→ ownership；
- `canSee` 返回值 + 调用方 throw → tenant；
- `@PreAuthorize("hasRole('ADMIN')")` → role + implied authentication；
- `if (amount < 0) throw` → 不判守卫。

### 34.6 待做

- 跨文件 unresolved helper 的参数级解析（当前只给 candidate）；
- 条件里的逻辑组合（`&&` / `||`）目前都记 decision，worker 需看 condition 判断覆盖分支；
- 布尔 helper 只在调用方有拒绝路径时扫描，避免把普通查询方法误判为守卫；
- 全量指标：java-sec-code 28 possible / saas 33 possible，authentication gap 偏多
  （这些工程没有全局认证拦截器，属于结构提示，不是最终结论）。
