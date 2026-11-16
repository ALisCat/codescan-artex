package com.community.clinic.model;

import lombok.Data;

@Data
public class Doctor {
    private Long id;
    private String name;
    private Long deptId;
    private Long tenantId;
}
