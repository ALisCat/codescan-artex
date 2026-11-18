# CodeScan GitLab 项目模块开发计划

> 更新时间：2026-11-17  
> 状态：阶段 1（连接配置 + 项目主线 + HEAD 检查）、分支选择与阶段 2 全量审计骨架已落地；增量审计待接入。

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
- 创建项目审计运行和 Task，自动绑定源码并开跑；
- 成功后更新 `last_audited_commit`；
- 同一项目同一时间只允许一个准备中的运行；
- 增量请求明确返回 501，不静默降级为全量。

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
- 真实 GitLab `weiyang/javascantest` 验证：分支列表能读取 `master` / `test-branch`；使用 `test-branch` 创建一个临时项目（tracked_branch=test-branch，HEAD 69e4a1e9）后删除，验证同仓库不同分支不触发路径唯一冲突。

## 6. 下一步

1. 等用户填入真实 Token 后联调项目列表、添加项目、HEAD 检查；
2. 用真实 Java 项目验收全量审计（源码、commit、任务启动）；
3. 实现阶段 3 增量审计；
4. 补数据库级并发锁、项目审计运行历史展示与权限。
