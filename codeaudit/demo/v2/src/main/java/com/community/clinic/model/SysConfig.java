package com.community.clinic.model;

import lombok.Data;

@Data
public class SysConfig {
    private Long id;
    private Long tenantId;
    private String cfgKey;
    private String cfgValue;
}
