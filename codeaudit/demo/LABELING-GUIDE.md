# 标注模板

> 这份文件**不给实现者看**。代码写完后由我们逐接口标注。

## 字段

| 字段 | 取值 | 说明 |
|---|---|---|
| endpoint | `/api/...` | 接口路径 |
| method | GET / POST / ... | HTTP 方法 |
| vulnclass | file-upload / path-traversal / sql-injection / command-exec / ssrf / deserialization / xss / authz | 与矩阵类型一致 |
| verdict | vuln / safe / needs_more | vuln=确实可利用；safe=有有效校验；needs_more=静态不可判定（如委托外部） |
| file | `src/main/java/...` | 证据位置 |
| line | 数字 | 证据行 |
| control_at | `file:line` 或空 | safe 时必填：校验写在哪 |
| note | 文本 | 触发条件/绕过方式 |

## 模板

```csv
endpoint,method,vulnclass,verdict,file,line,control_at,note
/api/appointment/{id},GET,authz,vuln,,,,"无归属校验"
/api/appointment/{id}/sec,GET,authz,safe,,,,"Service 层比对 patient_id"
```

## 标注原则

1. **只标已读过的**：没读到的代码不要猜
2. **safe 必须有 control_at**：找不到校验位置就标 needs_more
3. **一个接口可以有多个类型**：每个类型一行
4. **同一处代码被多个类型命中时**：主类型标 vuln，其余标 safe 并在 note 写"同根因，见主类型"
5. **委托外部校验**（如 HIS）：标 needs_more，note 写"需确认外部服务是否校验"

## 覆盖要求（v1 目标）

| 类型 | 至少条数 |
|---|---|
| authz | 4（2 vuln + 2 safe） |
| file-upload | 2（1 vuln + 1 safe） |
| path-traversal | 2 |
| sql-injection | 2 |
| ssrf | 1 |
| xss | 1 |
| command-exec 或 deserialization | 1 |
| 不适用对照（N/A） | 2 |

如果实现出来的代码缺某一类，说明业务规格没覆盖到，补需求后重新实现一版。
