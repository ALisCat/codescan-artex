package com.community.clinic.model;

import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDate;

@Data
public class Appointment {
    private Long id;
    private Long patientId;
    private Long doctorId;
    private LocalDate regDate;
    private String timeRange;
    /** PENDING 待就诊 / CANCELLED 已取消 / FINISHED 已完成 */
    private String status;
    private BigDecimal fee;
    private Long tenantId;
}
