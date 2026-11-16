package com.community.clinic.model;

import lombok.Data;

@Data
public class Patient {
    private Long id;
    private String name;
    private String phone;
    private String password;
    private String idCard;
    private Long tenantId;
}
