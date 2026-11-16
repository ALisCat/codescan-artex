package com.community.clinic.model;

import lombok.Data;

@Data
public class Dept {
    private Long id;
    private String name;
    private Long tenantId;
}
