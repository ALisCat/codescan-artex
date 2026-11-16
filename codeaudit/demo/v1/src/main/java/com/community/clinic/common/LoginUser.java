package com.community.clinic.common;

import lombok.Data;

/**
 * 登录用户，序列化后存 Redis（clinic:token:&lt;token&gt;）。
 */
@Data
public class LoginUser {

    private Long id;
    private String name;
    private String phone;
    /** PATIENT / DOCTOR / ADMIN */
    private String role;
    private Long tenantId;
    private String token;
}
