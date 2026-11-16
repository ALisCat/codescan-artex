# 社区诊所预约系统（clinic）

从旧系统接手重构的社区诊所预约后端，按 `DEMO-SPEC` 实现 12 个接口。

## 技术栈

- Java 8
- Spring Boot 2.7.18（Web / Data Redis）
- MyBatis 2.3.1（XML 与注解混用）
- PostgreSQL
- 单模块 Maven 工程，`groupId=com.community`，`artifactId=clinic`，包名 `com.community.clinic`

## 目录说明

```
pom.xml
src/main/java/com/community/clinic
├── ClinicApplication.java          启动类
├── common/                         统一返回、BizException、全局异常、登录用户上下文
├── config/                         配置属性、拦截器注册、密码编码器
├── interceptor/AuthInterceptor     token 校验 + 角色校验
├── controller/                     8 个 Controller，共 12 个接口
├── service/                        业务逻辑
├── mapper/                         MyBatis Mapper（注解 + XML 两种）
├── model/ dto/                     实体与请求对象
└── util/HisClient.java             HIS 对接（HTTP + JSON）
src/main/resources
├── application.yml                 数据源 / Redis / 上传 / 白名单
├── schema.sql                      建表 + 演示数据（幂等）
└── mapper/AppointmentMapper.xml, ArchiveMapper.xml
```

## 启动步骤

1. 准备 PostgreSQL（建议 12+）与 Redis（5+）：

```bash
createuser clinic -P            # 密码设为 clinic，或自行修改 application.yml / 环境变量
createdb clinic -O clinic
```

2. 建表：`schema.sql` 已配置为应用启动时自动执行（`spring.sql.init.mode=always`，脚本幂等）；
   也可以手动执行：

```bash
psql -h localhost -U clinic -d clinic -f src/main/resources/schema.sql
```

3. 按环境覆盖连接信息（默认值见 `application.yml`）：

```bash
export DB_HOST=localhost DB_PORT=5432 DB_NAME=clinic DB_USER=clinic DB_PASSWORD=clinic
export REDIS_HOST=localhost REDIS_PORT=6379
```

4. 打包启动：

```bash
mvn -q -DskipTests package
java -jar target/clinic-1.0.0.jar
```

5. 健康检查：

```bash
curl http://localhost:8080/api/health
# {"ok":true}
```

上传目录默认为 `/data/clinic/upload`，需要保证运行用户可写（或修改 `clinic.upload-dir`）。

## 演示账号

种子数据中的账号密码统一为 `password`（库中存 BCrypt 哈希）。

| 角色 | 手机号 | 说明 |
|---|---|---|
| PATIENT | 13800000001 | 患者「王小明」，有 2 条预约（id=1 待就诊，id=2 已取消），档案 id=1 |
| DOCTOR | 13900000001 | 医生「张医生」 |
| ADMIN | 13900000009 | 系统管理员 |

登录：

```bash
curl -s -X POST http://localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"phone":"13800000001","password":"password"}'
# {"code":0,"msg":"ok","data":{"token":"<token>","role":"PATIENT"}}
```

后续请求带上 `token` 请求头：`-H 'token: <token>'`。token 存在 Redis 的 `clinic:token:<token>`，有效期 24 小时。

## 接口一览

| # | 方法 | 路径 | 说明 | 角色 |
|---|---|---|---|---|
| 1 | POST | /api/auth/login | 登录，返回 token 与角色 | 公开 |
| 2 | GET | /api/appointment/{id} | 预约详情（患者姓名/医生/科室/时间/金额） | 登录 |
| 3 | GET | /api/appointment/list | 当前患者预约分页列表 | 患者 |
| 4 | POST | /api/appointment/cancel | 取消预约（仅待就诊），并调用 HIS 退款 | 登录 |
| 5 | POST | /api/appointment/{id}/reschedule | 改约，校验号源 | 登录 |
| 6 | POST | /api/file/upload | 上传附件（≤10MB） | 登录 |
| 7 | GET | /api/file/download | 下载附件 | 登录 |
| 8 | GET | /api/report/appointments | 预约统计 CSV | 管理员 |
| 9 | POST | /api/notice/send | webhook 群发通知并落库 | 管理员 |
| 10 | POST | /api/admin/config | 写 sys_config | 管理员 |
| 11 | GET | /api/external/patient-card | 调 HIS 查就诊卡 | 登录 |
| 12 | GET | /api/health | 健康检查 | 公开 |

统一返回：`{"code":0,"msg":"ok","data":...}`；失败时 code 非 0，HTTP 状态仍为 200。
例外：`/api/health` 返回 `{"ok":true}`，报表接口直接返回 CSV 文件流。

## 其它约定

- 预约状态：`PENDING`（待就诊）、`CANCELLED`（已取消）、`FINISHED`（已完成）。
- 号源上限取 `sys_config` 的 `appointment.capacity`，缺省 20。
- 列表接口返回 `{"total":..,"page":..,"pageSize":..,"list":[..]}`。
- 白名单配置在 `application.yml` 的 `clinic.auth.whitelist`。

## HIS 对接约定

`HisClient` 统一走 HTTP + JSON，地址取 `sys_config` 的 `his.base_url`（种子值 `http://localhost:9000/his`）。

- 退款：`POST {his.base_url}/refund`，body `{"appointmentId":1,"fee":35.00}`，响应 `{"code":0,"msg":"ok"}`；code 非 0 视为失败。
- 就诊卡：`GET {his.base_url}/patientCard?archiveId=1`，响应 `{"code":0,"msg":"ok","data":[...]}`，接口返回 `data` 部分。

本地没有 HIS 时，取消预约会返回“HIS 退款接口调用失败”，可先用一个桩服务占位。
