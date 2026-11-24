# 大项目扫描问题与优化方案

## 问题记录

项目：

```text
CBD/gxgyfy-digital-hospital-servers
branch: release-prod
commit: cf860b5
project id: 13
audit run: 31
task: 490
```

规模：

```text
Java 文件：9163
源码：约 592 MB
接口：3207
矩阵格：53656
可审计格：3748
N/A：44930
未验证：4978
```

矩阵生成耗时约 13～15 分钟：

```text
源码下载/解压：约 28 秒
CallGraphDump / JavaParser：约 8 分 32 秒
分析器 + binder：约 2 分 39 秒
矩阵导入 + 意图生成：约 3 分 11 秒
```

主要问题：

1. 矩阵规模爆炸：3207 接口 × 17 类漏洞，5.4 万格；N/A 仍全部写库。
2. 派发意图过多：3748 个可审计格，3 个 worker，完整跑完需要数十小时。
3. authz/SSRF 占比过高：authz 2521、SSRF 805，其他类型合计约 400。
4. `matrix_merge_dispatch=false` 时一个格一个意图，启动开销和 LLM 成本最高。
5. 大接口 worker 容易 `exhausted`，没有自动拆分/续审策略。
6. 任务暂停后项目审计 run 仍为 `running`，项目审计锁不释放。
7. UI 阶段粒度粗：下载、调用图、矩阵导入都显示为“下载源码”。
8. CallGraph 单线程，6g 堆可用但 8g 在 15G 机器上风险较高。
9. 缺少扫描前成本预估：用户看不到接口数、意图数、预计工时和 token 范围。

## 优化方案

### 阶段 1：立即止血

- 支持取消审计运行（任务暂停时释放项目审计锁）。
- 默认开启矩阵合并派发（`matrix_merge_dispatch=true`）。
- 扫描前展示接口数、可审计格数、预计意图数、预计工时和 token 范围。
- 超阈值扫描要求人工确认。

### 阶段 2：缩小矩阵与派发规模

- 增加扫描档位：快速 / 标准 / 深度。
- authz 按 Controller / 前缀聚合，不按每个接口单独派 2000+ 意图。
- SSRF 按 sink / HTTP 客户端聚合。
- 优先支付、挂号、病历、退款、管理端等高价值接口。
- N/A 格只保留统计或延迟生成，减少 4.5 万行导入。
- 意图按优先级分批生成，避免一次性创建 3000+。

### 阶段 3：生成性能

- CallGraph 按 repository + commit 缓存，同一 commit 重试可跳过约 8 分钟。
- 矩阵导入单事务已实现；下一步按 200～500 行批量 INSERT 或 COPY。
- 中期并行解析 Java 文件；注意 JavaParser symbol solver 线程安全。
- 扫描阶段在 UI 中分阶段展示：下载 / 调用图 / 分析器 / 绑定 / 导入 / 启动。

### 阶段 4：Worker 效率与成本

- worker 并发按 LLM 限流和机器内存动态调度。
- exhausted 意图自动拆分/续审，禁止原样重派。
- 任务级最大意图数、最大 token、最大时长预算。
- 达到预算自动暂停并提示。

## 推荐顺序

```text
1. 取消 run / 释放审计锁
2. matrix_merge_dispatch=true
3. 扫描前成本预览
4. 快速/标准/深度档位
5. authz/SSRF 聚合派发
6. N/A 延迟入库
7. CallGraph commit 缓存
8. 并行调用图解析
```

## 当前进展（2026-11-24）

- 所有非终态任务已确认处于 paused，未运行 worker。
- run #31 已取消，项目审计锁已释放。
- `matrix_merge_dispatch` 已设为 `true`。
- DB 矩阵导入已改为单事务提交。
- 项目详情增加“结束审计”入口，取消 run 时暂停执行任务。

### 已完成的扫描前预估

- 新增 `GET /api/projects/{id}/scan-estimate`。
- 基于最新矩阵统计接口数、可审计格、预计意图、worker 数、预计工时和 N/A/未验证数量。
- 项目详情“发起全量审计”卡片显示当前扫描档位的预估。
- 预估已按 authz Controller / SSRF sink 聚合派发计算，和实际 generate-intents 逻辑一致。

### 扫描档位（2026-11-24）

- 快速 / 标准 / 深度三档；默认标准档。
- 快速档：只保留高价值接口的 authz、P0/P1 的 SSRF，以及认证/SQL 注入/上传/路径穿越/命令执行/反序列化/XXE/密钥/加密/依赖/敏感数据等高信号类型。
- 标准档：保留全部非 authz/SSRF 类型；authz 只保留敏感业务接口；SSRF 只保留 P1 或 URL/回调类参数。
- 深度档：全部可审计格。
- 发起前如果预计意图 > 800 或 ETA > 10 小时，浏览器会要求人工确认。
- 当前项目 13 实测预估：

```text
快速：1214 可审计格 / 1120 接口 / 414 意图 / 3 worker / 约 4.6 小时
标准：1665 可审计格 / 1376 接口 / 623 意图 / 3 worker / 约 6.9 小时
深度：3748 可审计格 / 2663 接口 / 1129 意图 / 3 worker / 约 12.5 小时
```

### authz / SSRF 聚合派发

- `matrix_aggregate_authz=true`（默认）：authz 按 Controller 聚合，每组最多 8 格。
- `matrix_aggregate_ssrf=true`（默认）：SSRF 按 sink 文件/API 聚合，每组最多 6 格。
- 聚合只改变意图边界，矩阵仍保留逐格记录和逐格 verdict；worker 在一个意图里对每个 cell_key 分别提交结论。
- 对照：深度的预计意图从 2669 降到 1129。

### N/A 延迟导入

- `matrix_lazy_na_import=true`（默认）：大于 2000 格的导入先写可审计格并生成意图，N/A 行在后台补齐。
- 任务启动不再等待 4.5 万行 N/A 插入；矩阵统计会在后台导入完成后刷新。
- 失败只记录日志，不影响已启动的扫描。

### CallGraph commit 缓存

- `matrix.graph.build` 新增 `--cache-dir`；按 Java 源码内容哈希缓存 `callgraph.json`。
- 缓存位于 `data/cache/callgraph/<sha256>.json`，同一 commit 重试命中后跳过 JavaParser 阶段。
- 已用 fixture 验证：首次 1.6s，命中 0.08s；大项目预计节省约 8 分钟。
- 缓存版本 `callgraph-v2`；Java 工具升级时需提升版本号。
