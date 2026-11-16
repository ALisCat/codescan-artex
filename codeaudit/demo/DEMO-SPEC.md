# 社区诊所预约系统 · 需求规格（给实现者）

> 本文只描述**业务功能**，不含任何安全要求、漏洞清单或检测规则。
> 实现时按"能跑通业务"的标准写即可；这是一个从旧系统接手重构的项目，
> 各部分代码质量可能不一致，请不要刻意统一风格。

## 1. 技术栈

- Java 8
- Spring Boot 2.7
- MyBatis（部分查询用 XML，部分用注解）
- PostgreSQL
- 单模块 Maven 工程，包名 `com.community.clinic`

## 2. 角色与数据

| 角色 | 说明 |
|---|---|
| 患者 | 手机号 + 密码登录；只能操作自己的预约与档案 |
| 医生 | 查看自己的排班与预约 |
| 管理员 | 系统配置、通知群发 |

主要表：

```
patient(id, name, phone, password, id_card, tenant_id)
doctor(id, name, dept_id, tenant_id)
appointment(id, patient_id, doctor_id, reg_date, time_range, status, fee, tenant_id)
archive(id, patient_id, id_card, phone, tenant_id)
attachment(id, patient_id, file_name, file_path, upload_time)
notice(id, title, content, channel, created_by)
sys_config(id, tenant_id, cfg_key, cfg_value)
```

## 3. 接口清单（共 12 个）

### 3.1 认证

**POST /api/auth/login**

请求：`{"phone":"...","password":"..."}`
响应：`{"token":"...","role":"PATIENT|DOCTOR|ADMIN"}`

登录成功后把用户信息放进 Redis，key 形如 `clinic:token:<id>`；
后续请求由拦截器从 `token` 请求头取用户。

### 3.2 预约

**GET /api/appointment/{id}**

返回预约详情：患者姓名、医生、科室、时间、金额。

**GET /api/appointment/list**

参数：`status`（可选）、`beginDate`、`endDate`、`page`、`pageSize`
返回当前患者的预约列表（分页）。

**POST /api/appointment/cancel**

请求：`{"appointmentId":123}`
校验预约状态（仅"待就诊"可取消），更新为"已取消"，并调用 HIS 退款接口。

**POST /api/appointment/{id}/reschedule**

请求：`{"regDate":"2026-12-01","timeRange":"09:00-10:00"}`
校验目标时段是否还有号源，更新预约时间。

### 3.3 文件

**POST /api/file/upload**

表单字段 `file`（MultipartFile），以及 `archiveId`。
保存到 `/data/clinic/upload/<archiveId>/`，返回文件名。
限制单文件不超过 10MB。

**GET /api/file/download**

参数：`path`（文件相对路径）
返回文件流，供患者下载检查报告。

### 3.4 报表

**GET /api/report/appointments**

参数：`sort`（排序字段，默认 reg_date）、`order`（asc/desc）
返回统计报表（CSV）。管理员使用。

### 3.5 通知

**POST /api/notice/send**

请求：`{"title":"...","content":"...","webhook":"https://..."}`
把通知内容 POST 到指定 webhook（社区医院的公众号网关），
并记录到 notice 表。

### 3.6 管理

**POST /api/admin/config**

请求：`{"key":"...","value":"..."}`
写入 sys_config。仅管理员可调用。

### 3.7 外部对接

**GET /api/external/patient-card**

参数：`archiveId`
调用 HIS 的 `patientCard` 接口，返回该档案下的就诊卡列表。
HIS 地址从 sys_config 读取（`his.base_url`）。

### 3.8 健康检查

**GET /api/health**

返回 `{"ok":true}`。

## 4. 其他要求

- 统一返回 `{"code":0,"msg":"ok","data":...}`
- 拦截器负责登录与角色判断，路径白名单写在 `application.yml`
- HIS 调用统一走 `HisClient` 工具类（HTTP + JSON）
- 所有 SQL 都写在 Mapper 层
- 错误统一抛 `BizException`，由 `@RestControllerAdvice` 处理
- 不需要写单元测试

## 5. 交付

- 可编译的 Maven 工程（`mvn -q -DskipTests package` 通过）
- `src/main/resources/schema.sql` 建表脚本
- 一个 README 说明如何启动
