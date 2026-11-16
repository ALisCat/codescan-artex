package com.community.clinic.model;

import lombok.Data;

/**
 * 医生 / 管理员登录账号（patient 表只存患者）。
 */
@Data
public class SysUser {
    private Long id;
    private String name;
    private String phone;
    private String password;
    /** DOCTOR / ADMIN */
    private String role;
    private Long tenantId;
}
