# CodeScan GitLab 项目模块开发计划

> 更新时间：2026-11-17  
> 状态：阶段 1、分支选择、阶段 2 全量审计、阶段 2.5 增量预览已落地；真正的增量审计待接入。

## 1. 目标

在 CodeScan 中把 GitLab 仓库作为长期审计对象，而不是每次新建任务都重新上传 zip：

```
项目 Project
  └── 审计运行 AuditRun（full | incremental）
        └── 任务 Task（现有矩阵审计流水线）
```

- 项目以「仓库 + 审计分支」为身份：同一仓库的 `master`、`test-branch` 等可分别建成不同项目；
- 全量审计建立源码与矩阵基线；
- 增量审计以最近一次成功审计的 commit 为 base，只派发受变更影响的接口/矩阵格；
- 每天只检查项目目标分支 HEAD 是否有新 commit，不自动下载源码、不自动建任务；
- 所有审计运行固定到 commit SHA，保证结论可回溯。

## 2. 已落地（阶段 1）

### 2.1 系统级 GitLab 连接

- 一个系统地址 + 一个 service account PAT；
- 管理员在「系统配置 → GitLab 代码源」填写；
- Token 只写不读，接口只回显 `gitlab_token_set` 和末四位 hint；
- 测试连接调用 `GET /api/v4/user`，不把 Token 写进 URL 或日志；
- 地址只保留 origin，拒绝 `user:pass`、query、fragment；
- 客户端重定向限制在同一 origin。

### 2.2 项目模型

表 `code_projects`：

- `path`、`gitlab_project_id`、`web_url`、`default_branch`；
- `tracked_branch`：项目实际跟踪/审计的分支；唯一键为 `(path, tracked_branch)`；
- `last_seen_commit`：最近一次检查到的目标分支 HEAD；
- `last_audited_commit`：最近一次成功全量/增量的目标 commit；
- `last_checked_at`、`last_check_error`、`status`；
- 创建者、创建/更新时间。

### 2.3 API

```
POST /api/settings/gitlab/test        测试连接（管理员）
GET  /api/gitlab/projects             列出当前 Token 可见项目（管理员）
GET  /api/gitlab/projects/lookup      按路径解析项目（管理员）
GET  /api/gitlab/projects/{id}/branches  列出项目分支（管理员）
GET  /api/projects                    项目列表
POST /api/projects                    添加项目（管理员；body 含 name/branch）
GET  /api/projects/{id}               项目详情
POST /api/projects/{id}/check         手动检查目标分支 HEAD（管理员）
DELETE /api/projects/{id}             删除项目（管理员）
```

### 2.4 UI

- 侧边栏「对话 → 项目 → 任务」；
- 项目列表：搜索、添加、检查更新、状态（未审计 / 有更新 / 已审计）；
- 添加项目：先选择/解析 GitLab 仓库，再选择审计分支，最后填写项目名称；
- 同一仓库不同分支可分别创建项目，默认名称带分支后缀；
- 分支在项目创建时确定，避免改变已有审计基线；需要其他分支时新建项目；
- 项目详情：目标分支、HEAD、最近成功审计 commit、更新状态；
- 系统配置：GitLab 地址、Token、测试连接、清除 Token；
- 未配置 Token 时项目页明确提示并跳转系统配置。

### 2.5 每日检查

- 服务启动后 5 分钟首次执行，之后每 24 小时一次；
- 只对每个项目的 `tracked_branch` 调用 branch HEAD；
- 只更新 `last_seen_commit` / `last_checked_at` / `last_check_error`；
- 不下载源码、不创建任务、不修改 `last_audited_commit`。

### 2.6 全量审计（阶段 2 骨架）

- `POST /api/projects/{id}/audit`，当前只接受 `mode=full`；
- 固定 `tracked_branch` HEAD 的 commit 下载 GitLab archive；
- 复用 `task_uploads` staging + 解压逻辑；
- 源码绑定后自动运行矩阵流水线（graph → analyzers → bind → import），导入 `ca_cells` 并生成矩阵意图，然后再启动 Task；
- 创建项目审计运行和 Task，自动绑定源码并开跑；
- 成功后更新 `last_audited_commit`；
- 同一项目同一时间只允许一个准备中的运行；
- 增量请求明确返回 501，不静默降级为全量；
- 矩阵分析器目录通过 `ARTEX_CODEAUDIT_DIR` 或 `src/codeaudit` 自动定位；矩阵生成失败时审计运行失败，不静默退回标准 planner。

新增表 `project_audit_runs`：

- `project_id`、`mode`、`base_commit`、`target_commit`、`task_id`；
- `status`（fetching / ready / failed）、`error_message`；
- 项目详情可轮询运行状态并跳转任务。

## 3. 待开发

### 阶段 2 剩余验收

- 无 Token / Token 无效 / 项目不可见时不留下半成品任务；
- 真实 GitLab 大仓库下载超时与断点行为；
- 失败后的 staging 清理与审计运行状态回写；
- 任务详情展示项目、commit、审计模式；
- 并发审计互斥已做进程内前置检查，数据库级锁待补。

### 阶段 2.5：增量变更预览（已实现）

安全工程师在发起增量前，需要先判断变更范围是否值得跑增量。因此先做只读预览，不创建任务、不下载完整源码、不启动 LLM。

已实现接口：

```text
GET /api/projects/{id}/change-preview
```

已实现位置：

- 后端 `server/project_preview.go`；
- 前端项目详情页「增量分析」卡片；
- `matrix` 解析不参与预览，预览只做 compare + changed Java raw。

输入：

- `base_commit`：项目最近一次成功审计的 commit；
- `target_commit`：`tracked_branch` 当前 HEAD；
- 无 base 时返回 `needs_full: true`；
- base == target 时返回 `no_changes: true`。

输出：

- 提交列表：sha、标题、作者、时间；
- 变更摘要：文件数、新增行、删除行；
- 文件列表：`old_path`、`new_path`、状态（new/modified/deleted/renamed）、新增/删除行数；
- 每个文件的 hunk：旧起点/行数、新起点/行数；
- 展开 diff：GitLab compare 返回的 unified diff 原文；
- 接口影响：
  - Controller 注解直接映射，标记 `direct`；
  - Service/Mapper/XML 只标记 `candidate`；
  - 配置/公共组件标记 `unmapped`；
- 告警：compare 超时、diff 截断、非祖先/force push、二进制文件、无变更、无基线。

约束：

- 只调用 compare，不下载完整 archive；
- 只对变更的 Controller Java 文件按需拉 raw 内容做注解解析；
- 文件数/字节数设上限，超限时只展示文件级摘要并提示需要全量；
- diff 不写日志、不持久化完整源码；
- 预览完成前“发起增量审计”保持不可用；
- 预览结果不能当作“安全结论”，只用于判断是否值得发起增量。

UI：

- 项目详情新增「增量分析」卡片；
- 展示 base/target、提交数、文件数、+/- 行数；
- 文件列表可展开 hunk 和具体 diff；
- 接口影响分为直接/候选/无法映射；
- 增加“预览变更”按钮，显示加载中和失败原因。

已验收：

- `no_changes`、`needs_full` 分支可用；
- diff 行数/hunk 解析和 Spring 注解接口映射有单元测试；
- 项目详情卡片可展示提交、文件、hunk、diff、直接接口和告警；
- 不下载完整 archive、不创建任务、不启动 LLM；
- compare 失败时提示回退全量。

### 阶段 3：增量审计

1. 计算 base：项目最近一次成功审计的 commit；
2. 无 base、base 非祖先、base 源码不可用时拒绝增量，要求先全量；
3. 使用 GitLab API：
   - `GET /repository/compare?from=base&to=target`
   - `GET /repository/files/:path/raw?ref=...`
4. base 源码快照 overlay 变更文件，形成 target 工作树；
5. 变更文件映射到受影响接口/矩阵格；
6. 只派发 delta cells，base findings 只读继承；
7. compare 失败或 diff 过大时回退全量。

验收：

- 增量任务不会重复全仓分析；
- 目标 commit 与 compare 的 target 一致；
- 非祖先/force push 时强制全量；
- 任务详情能看到变更文件、受影响接口/格、delta/baseline findings。

### 阶段 4：运行记录与权限

1. `project_audit_runs` 表：project_id、mode、base_commit、target_commit、task_id、状态、统计；
2. 项目详情展示审计运行历史；
3. 平台权限模型完成后：
   - 连接配置仅管理员；
   - 项目按部门/所有者授权；
   - 审计运行继承项目权限；
4. Token 存储升级为加密存储 + 轮换提示。

## 4. 安全与边界

- Token 只在服务端使用，不进入 URL、日志、前端 payload；
- GitHub/GitLab 项目路径只接受 `group/project` 形状，禁止任意 URL；
- 所有下载固定 commit SHA；
- 不自动执行仓库代码、不编译、不运行应用；
- 增量基线源码快照不可自动清理；
- 每日检查失败只记录错误，不改变审计基线；
- 大仓库超时/失败时不自动降级为“部分成功”。

## 5. 当前验证

- `go test ./gitlabsrc`：Token header、项目/分支查询、401、非法 base URL；
- `go test ./server -run '^$'`：编译通过；
- 前端 `npm run build:static`：`/function/projects` 与详情页成功导出；
- 8789 环境：`/api/settings` 回显 GitLab 配置字段，`/api/projects` 可访问，假 Token 测试返回 401，清除后恢复未配置；
- `projects-phase2c` 已部署到 8789，项目审计运行表与 `POST /api/projects/{id}/audit` 路由可用；
- 使用 mock GitLab（自建 archive.zip）完成一次端到端全量审计：项目创建 → HEAD → 下载/解压 → 任务创建 → 源码绑定 → `last_audited_commit` 回写 → 清理任务/项目，验证通过；
- 真实 GitLab `weiyang/javascantest` 验证：分支列表能读取 `master` / `test-branch`；使用 `test-branch` 创建一个临时项目（tracked_branch=test-branch，HEAD 69e4a1e9）后删除，验证同仓库不同分支不触发路径唯一冲突；
- 修复 unlimited 解压路径：`io.LimitReader(rc, -1)` 会立即 EOF，导致全量审计源码目录出现 53 个 0 字节文件；改为 unlimited 时直接读原始 reader，并增加非空文件门禁与回归测试；
- 项目全量审计已自动生成矩阵：任务 #24 在约 4 秒内完成 graph/analyzers/bind/import，得到 204 格（18 applicable / 153 N/A / 33 unverified）并生成 18 个矩阵意图；任务 #23 是修复前的标准 planner 路径，已暂停。

## 6. 下一步

1. 等用户填入真实 Token 后联调项目列表、添加项目、HEAD 检查；
2. 用真实 Java 项目验收全量审计（源码、commit、任务启动）；
3. 实现阶段 3 增量审计；
4. 补数据库级并发锁、项目审计运行历史展示与权限。
