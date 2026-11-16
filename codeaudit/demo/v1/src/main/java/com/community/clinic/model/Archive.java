package com.community.clinic.model;

import lombok.Data;

@Data
public class Archive {
    private Long id;
    private Long patientId;
    private String idCard;
    private String phone;
    private Long tenantId;
}
