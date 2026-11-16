# demo 评测结果（规则有效性）

> 真实业务语料只能看"像不像"，不能算准确率。这里用**有 ground truth** 的 demo
> 验证矩阵规则本身：召回够不够、误派多不多、守卫降级会不会误杀。

## 语料

| 版本 | 来源 | 规模 | ground truth |
|---|---|---|---|
| v1 | 按 `DEMO-SPEC.md` 盲写 | 12 接口 / 96 格 | **1 个真漏洞**（notice/send SSRF），其余 safe/na |
| v2 | v1 + 5 处机械变异 | 12 接口 / 96 格 | **10 个真漏洞** |

v2 变异（都在 `demo/v2` 里，可直接 diff）：

| # | 文件 | 变异 | 种下的漏洞 |
|---|---|---|---|
| M1 | `AppointmentService.detail` | 删除 `checkOwner` | 水平越权（读同租户他人预约） |
| M2 | `FileService.download` | 直接 `Paths.get(path)`，删除 baseDir/startsWith 与附件归属 | 任意文件读取 |
| M3 | `ReportService.buildCsv` | 去掉 `normalizeSort`，sort/order 原样进 `${}` | SQL 注入 |
| M4 | `AuthInterceptor` | 删除 `"ADMIN".equals(role)` 校验 | 垂直越权（admin/report/notice） |
| M5 | `FileService.upload` | 原始文件名直接落盘，去掉 cleanPath/../UUID | 任意文件写入 + 路径穿越 |

## 指标

### v1（安全版，应该"几乎不派"）

| 指标 | v1.2 | v1.3 |
|---|---|---|
| 派单 | 17 | **1** |
| 召回 | 1/1 | **1/1** |
| 误派 | 16/17 = **94%** | **0/1 = 0%** |
| hold（可见不派） | — | 14 |
| 未验证 | 7 | 8 |

### v2（变异版，应该"该派的都派"）

| 指标 | v1.2 | v1.3 |
|---|---|---|
| 派单 | 16 | **10** |
| 召回 | 9/9 | **10/10** |
| 误派 | 7/16 = **44%** | **0/10 = 0%** |
| hold（可见不派） | — | 5 |

> v1.5 的 10 个派单恰好就是 10 个真漏洞，误派为 0，召回未掉。
> （v1.5 补了「文件读写也算资源」：M2 同时删掉归属校验，`/api/file/download` 的 authz 之前被判 N/A，现已补上。）

### 回归：真实语料没有被改坏

| 语料 | 派单 | 召回 | 误派/hold | 验收 |
|---|---|---|---|---|
| java-sec-code | 77 → **79** | **23/23** | hold 3（全部 sec 变体） | R1/R2/R3 PASS |
| saas-git | 36 → **36** | — | hold 0（tenantId 来自请求体，本就该审） | — |

## v1.3 的规则变化

1. **守卫感知的 hold**：已有结构性守卫的格子写进矩阵、标 `hold`，但不派单。
   - 归属校验（`checkOwner` / `Objects.equals(resource.getPatientId(), user.getId())`）
   - 路径限制（`startsWith` / `getCanonicalPath` / `cleanPath + ..`）
   - 参数化查询 / 排序白名单
   - 文件名 UUID 重命名 + 净化
2. **只对"结构性守卫"放行**：SSRF 域名白名单、上传后缀白名单这类**可能被绕过**的
   名字型白名单，只有在接口命名明确是 `sec/safe/valid/security` 变体时才 hold。
3. **公开的登录/健康接口不做 authz**。
4. **sink 类型收窄**：
   - `Paths.get(dir, archiveId)` 里 `archiveId` 是 `Long` → 不算路径穿越
   - 显式 `Content-Type: text/csv` 的 `getWriter()` → 不算 XSS
5. **全局鉴权策略**：解析 `WebMvcConfig` + 拦截器里的 `"ADMIN"` 角色校验与
   `/api/admin/**` 等前缀；有校验 → 管理员接口的 authz 降为 hold；校验被删 → applicable。

## 已知风险（必须说清）

- **v2 是 v1 的变异，不是独立盲写**。规则是在 v1 上调的、在 v2 上验的，
  仍有"按答案调参"的成分。真正的 holdout 需要按同一份 spec 让另一个实现者写 v3（不看规则）。
- **hold 不是"安全"**：它只是"先不烧 token"。守卫可能写错、可能可绕过；
  hold 的格子仍在矩阵里，必要时用 `--low` 重新生成或手动派单。
- 归属校验的错误用法（比错字段、只比租户不比用户）会被 hold 漏掉；
  这是当前最大的召回风险，需要 v3 专门种这类变异来测。

## 复现

```bash
# 生成矩阵
python3 tools/cellgen.py demo/v1 /tmp/demo-v1-out
python3 tools/cellgen.py demo/v2 /tmp/demo-v2-out

# 对比 ground truth
python3 tools/demo_eval.py /tmp/demo-v1-out demo/v1/GROUND-TRUTH.csv
python3 tools/demo_eval.py /tmp/demo-v2-out demo/v2/GROUND-TRUTH.csv

# 回归
python3 tools/acceptance.py /tmp/java/tasks.json <java-sec-code 源码> 120
```

## 下一步

1. 按 `DEMO-SPEC.md` 再盲写一版 **v3**（不看本文件、不看 cellgen 规则），
   专门种"错误归属校验 / 可绕过白名单 / 委托外部判定"三类。
2. 用 v3 只跑不调，作为 holdout；若 hold 误杀 > 10%，收紧 hold 规则。
3. 对 v2 的 9 个格子跑一次 worker，验证"方向对了"之后结论也对。
