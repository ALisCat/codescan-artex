# matrix：图 → 分析器 → worker

## 目录

```
matrix/
  graph/build.py        JavaParser + Spring + XML → graph.json
  context.py            读图 + 按 file:line 读源码
  analyzers/base.py     Analyzer / Finding 契约
  analyzers/*.py        每类漏洞一个分析器
  guards/               语义守卫：principal/resource/条件/拒绝路径 + 全局策略
  catalogs/*.yaml       sink / 守卫 / 资源 模式
  run.py                跑分析器，输出 findings.json
```

## graph.json（v1.0）

```json
{
  "version": "1.0",
  "root": "/path/to/source",
  "stats": {"endpoints": 35, "flow_steps": 727, "endpoints_with_dao": 19},
  "endpoints": [
    {
      "id": "POST /api/...",
      "method": "POST", "url": "/api/...",
      "handler": "getDept", "file": "...", "line": 33,
      "params": [{"name": "...", "type": "...", "location": "body"}],
      "flow": [
        {"kind": "method", "method_id": "...", "cls": "...", "name": "...", "file": "...", "line": 33, "end": 36},
        {"kind": "dao", "cls": "...DeptMapper", "name": "selectList", "file": "...", "line": 77, "sql_kind": "wrapper"}
      ],
      "daos": [
        {"dao": "...DeptMapper", "method": "selectList", "sql_kind": "wrapper",
         "sql_site": null, "wrapper": [{"name": "eq", "file": "...", "line": 77, "scope": "wrapper"}]}
      ],
      "unresolved": [{"file": "...", "line": 77, "name": "selectList", "scopeText": "deptMapper"}]
    }
  ],
  "classes": [...], "fields": [...], "methods": [...], "calls": [...], "xml_sites": [...]
}
```

## 分析器契约

```python
class Analyzer:
    vulnclass = "..."
    def analyze(self, endpoint, ctx) -> list[Finding]
```

Finding：

```json
{
  "endpoint_id": "POST /api/...",
  "vulnclass": "authz",
  "state": "possible | impossible | unknown",
  "evidence": {"resource_accesses": [...], "params": [...]},
  "guards_seen": [{"kind": "ownership", "file": "...", "line": 86, "text": "..."}],
  "missing": "unresolved: ..."
}
```

规则：

- 分析器只回答"结构上有没有该类 sink / 资源访问"；
- **不做**污点、可达性、白名单、防护判断；
- `guards_seen` 只记录，不改变 state；
- `impossible` 必须给结构证据；
- `unknown` 必须说明缺哪一段（未解析调用/file:line）。

## 状态含义

| state | 含义 | 去向 |
|---|---|---|
| possible | 流程里找到了该类 sink | 派给 worker |
| impossible | 流程里没有该类 sink | 不派 |
| unknown | 图不完整，sink 可能藏在未解析调用后 | 最低优先级/可选 |

## guards：语义守卫（v0.1）

`matrix/guards/` 不按方法名判断守卫，而是按行为签名：

```
principal 来源 + resource/role 参与条件 + 拒绝路径
```

| 文件 | 作用 |
|---|---|
| `scan.py` | 从方法源码抽取 principal/resource 变量、条件、throw/return 拒绝路径 |
| `engine.py` | 组装 `authz_model`：principal/resource/decisions/required/coverage/gaps |
| `policy.py` | 拦截器/WebMvc/Spring Security/租户插件/白名单 |

检测范围：

- inline：`if (Objects.equals(resource.ownerId, user.id)) throw`；
- helper：任意命名的方法体（`ensureAccess`、`validate`、`canSee`）；
- 返回值：`if (!canSee(order, user)) throw`，解析 `canSee` 方法体；
- 声明式：`@PreAuthorize` / `@Secured` / `@RolesAllowed` / Shiro / Sa-Token；
- 全局策略：`HandlerInterceptor`、`WebMvcConfigurer`、`SecurityFilterChain`、`TenantLineHandler`；
- 死守卫：`needAdmin` 路径存在但 `preHandle` 未调用 → 记入 `required`/`unknowns`，不算 observed。

`authz_model` 示例：

```json
{
  "principal": {"var": "user", "type": "LoginUser", "source": "UserContext.require()", "file": "...", "line": 41},
  "resource": {"var": "order", "type": "Order", "source": "mapper.findById(id)", "file": "...", "line": 42},
  "decisions": [
    {"kind": "authentication", "rule": "principal or interceptor", "file": "...", "line": 34},
    {"kind": "ownership", "rule": "order.ownerId == user.id", "file": "...", "line": 46,
     "target_file": "...", "target_line": 129, "resolved": true}
  ],
  "required": ["authentication", "ownership"],
  "coverage": ["authentication", "ownership"],
  "gaps": [],
  "unknowns": []
}
```

`required` 是结构推导（资源 id → ownership；租户参数/插件 → tenant；admin/report 路径或策略声明 → role；资源访问 → authentication）。
`gaps = required - observed`，只作为 worker 的线索，不是最终结论。

`search_policy` 控制 worker 的全局搜索预算：

```json
{"allow_global_search": true, "search_budget": 2,
 "search_kinds": ["ownership"],
 "search_patterns": ["owner|patientId|userId|checkOwner|ensureAccess"]}
```

- required 中已命中的 kind 不再搜索；
- 缺失 kind 允许 Glob/Grep 合计 2 次定向搜索；
- `allow_global_search=false` 时移除 Glob/Grep；
- authz_model 格移除 LS/Write/Edit，禁止写笔记。

## 验收

- demo-v2：5 个种下 authz 漏洞全部出现在 `gaps`，6 个 safe 接口无 gap；
- demo-v1：全部无 gap；
- 改名 `checkOwner → ensureAccess` 后检测结果不变；
- fixture：任意命名 helper、返回值 helper、`@PreAuthorize`、业务校验（amount<0）不误判。
