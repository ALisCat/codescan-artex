# 评测协议 v1

## 目的

在不依赖大语料、不烧穿配额的前提下，回答三个问题：

1. 矩阵派的方向**全不全**（会不会漏）
2. 派出去的方向**值不值得看**（误派率、每格成本）
3. 在**没见过的代码**上是否仍然有效（泛化）

## 关键约束：盲写

```
实现者只能看 DEMO-SPEC.md
不能看：MATRIX-DESIGN.md、SINK 列表、标注文件、历史评测结果
```

> 否则就是"按答案出题"，测出来的只是规则的回声。

## 流程

### Step 1 生成代码（盲）

- 把 `DEMO-SPEC.md` 单独交给一个没有项目上下文的模型/人
- 要求：能编译、能启动、业务能跑通即可
- 允许代码风格不一致（规格里已声明是历史项目）

### Step 2 人工标注（我们）

按 `LABELING-GUIDE.md` 逐接口读代码，填 `ground-truth.csv`。

要求：
- 只标真实读到的
- `safe` 必须写清校验位置
- 委托外部的标 `needs_more`

### Step 3 跑矩阵

```bash
# 1) 上传 demo 源码 → 建任务（llm_profile_id 用便宜的那条）
# 2) 生成矩阵
python3 cellgen.py <demo源码目录> /tmp/opencode/demo

# 3) 导入（此时 matrix_merge_dispatch=false → 单格派发）
curl -X POST .../api/codeaudit/tasks/<id>/import -d @import_body.json
```

### Step 4 计算指标

| 指标 | 定义 | 目标 |
|---|---|---|
| **方向召回** | 标注为 vuln 的 (接口,类型) 中被派出的比例 | ≥ 90% |
| **误派率** | applicable 中标注为 safe/N/A 的比例 | ≤ 35% |
| **确认准确率** | 矩阵 confirmed 中人工判定真的比例 | ≥ 80% |
| **clean 证据率** | 判 clean 的格里写了正向证据的比例 | = 100% |
| **每格 token** | 输入 token / 已了结格数 | ≤ 250k |
| **每格轮次** | assistant 轮次 / 已了结格数 | ≤ 12 |

### Step 5 防过拟合

规则每改一轮，**不要重跑同一份代码**。做法：

- 保留 demo v1 作为回归集（只跑，不调）
- 调整规则后，用同一份 spec 让另一个实现者写 demo v2
- v2 上验证通过后，才允许把 v1 加回回归集

## 本轮已生效的成本开关

| 开关 | 值 | 作用 |
|---|---|---|
| `agents.worker.max_turns` | 15 | 单意图最多 15 轮，防止无限探索 |
| `settings.matrix_merge_dispatch` | false | 单格派发（demo 阶段） |
| 配额 blocked | 不回填 | 避免"429 → 重派 → 再 429"的空转 |

调回合并派发：

```sql
UPDATE settings SET value='true' WHERE key='matrix_merge_dispatch';
```

## 记录表

每轮结果追加到 `RESULTS.md`：

```
| 轮次 | demo | 格数 | 已了结 | 召回 | 误派 | 确认准确 | token/格 | 轮次/格 |
```
