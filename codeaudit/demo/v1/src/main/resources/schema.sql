-- 社区诊所预约系统 · PostgreSQL 建表脚本
-- 幂等：可重复执行（DDL 用 if not exists，种子数据用 on conflict do nothing）

create table if not exists dept (
    id        bigserial primary key,
    name      varchar(64) not null,
    tenant_id bigint      not null default 1
);

create table if not exists patient (
    id        bigserial    primary key,
    name      varchar(64)  not null,
    phone     varchar(20)  not null,
    password  varchar(100) not null,
    id_card   varchar(32),
    tenant_id bigint       not null default 1
);
create unique index if not exists uk_patient_phone on patient (phone);

create table if not exists doctor (
    id        bigserial   primary key,
    name      varchar(64) not null,
    dept_id   bigint,
    tenant_id bigint      not null default 1
);

-- 医生 / 管理员登录账号
create table if not exists sys_user (
    id        bigserial    primary key,
    name      varchar(64)  not null,
    phone     varchar(20)  not null,
    password  varchar(100) not null,
    role      varchar(16)  not null,
    tenant_id bigint       not null default 1
);
create unique index if not exists uk_sys_user_phone on sys_user (phone);

create table if not exists appointment (
    id         bigserial     primary key,
    patient_id bigint        not null,
    doctor_id  bigint        not null,
    reg_date   date          not null,
    time_range varchar(32)   not null,
    status     varchar(16)   not null default 'PENDING',
    fee        numeric(10,2) not null default 0,
    tenant_id  bigint        not null default 1
);
create index if not exists idx_appointment_patient on appointment (patient_id);
create index if not exists idx_appointment_slot on appointment (doctor_id, reg_date, time_range);

create table if not exists archive (
    id         bigserial   primary key,
    patient_id bigint      not null,
    id_card    varchar(32),
    phone      varchar(20),
    tenant_id  bigint      not null default 1
);

create table if not exists attachment (
    id          bigserial    primary key,
    patient_id  bigint       not null,
    file_name   varchar(255) not null,
    file_path   varchar(512) not null,
    upload_time timestamp    not null default now()
);

create table if not exists notice (
    id         bigserial    primary key,
    title      varchar(128) not null,
    content    text,
    channel    varchar(32),
    created_by bigint
);

create table if not exists sys_config (
    id         bigserial    primary key,
    tenant_id  bigint       not null,
    cfg_key    varchar(64)  not null,
    cfg_value  varchar(512)
);
create unique index if not exists uk_sys_config_key on sys_config (tenant_id, cfg_key);

-- ---------------------------------------------------------------------------
-- 种子数据（演示账号统一密码：password）
-- ---------------------------------------------------------------------------

insert into dept (id, name, tenant_id) values
    (1, '全科', 1),
    (2, '内科', 1)
on conflict (id) do nothing;

insert into doctor (id, name, dept_id, tenant_id) values
    (1, '张医生', 2, 1),
    (2, '李医生', 1, 1)
on conflict (id) do nothing;

insert into patient (id, name, phone, password, id_card, tenant_id) values
    (1, '王小明', '13800000001', '$2b$10$N9qo8uLOickgx2ZMRZoMye8fOsiTWZqYtkxvXkKm8BMzjT7t/vIdq', '110101199001011234', 1)
on conflict (id) do nothing;

insert into sys_user (id, name, phone, password, role, tenant_id) values
    (1, '张医生', '13900000001', '$2b$10$N9qo8uLOickgx2ZMRZoMye8fOsiTWZqYtkxvXkKm8BMzjT7t/vIdq', 'DOCTOR', 1),
    (2, '系统管理员', '13900000009', '$2b$10$N9qo8uLOickgx2ZMRZoMye8fOsiTWZqYtkxvXkKm8BMzjT7t/vIdq', 'ADMIN', 1)
on conflict (id) do nothing;

insert into archive (id, patient_id, id_card, phone, tenant_id) values
    (1, 1, '110101199001011234', '13800000001', 1)
on conflict (id) do nothing;

insert into sys_config (id, tenant_id, cfg_key, cfg_value) values
    (1, 1, 'his.base_url', 'http://localhost:9000/his'),
    (2, 1, 'appointment.capacity', '20')
on conflict (id) do nothing;

insert into appointment (id, patient_id, doctor_id, reg_date, time_range, status, fee, tenant_id) values
    (1, 1, 1, '2026-12-01', '09:00-10:00', 'PENDING', 35.00, 1),
    (2, 1, 2, '2026-11-20', '10:00-11:00', 'CANCELLED', 50.00, 1)
on conflict (id) do nothing;

-- 种子数据使用了显式 id，这里同步序列，避免后续插入主键冲突
select setval(pg_get_serial_sequence('dept', 'id'), (select max(id) from dept));
select setval(pg_get_serial_sequence('doctor', 'id'), (select max(id) from doctor));
select setval(pg_get_serial_sequence('patient', 'id'), (select max(id) from patient));
select setval(pg_get_serial_sequence('sys_user', 'id'), (select max(id) from sys_user));
select setval(pg_get_serial_sequence('archive', 'id'), (select max(id) from archive));
select setval(pg_get_serial_sequence('sys_config', 'id'), (select max(id) from sys_config));
select setval(pg_get_serial_sequence('appointment', 'id'), (select max(id) from appointment));
