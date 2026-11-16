package com.community.clinic.model;

import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * 预约详情视图（患者姓名、医生、科室、时间、金额）。
 */
@Data
public class AppointmentDetail {
    private Long id;
    private Long patientId;
    private String patientName;
    private String doctorName;
    private String deptName;
    private LocalDate regDate;
    private String timeRange;
    private String status;
    private BigDecimal fee;
}
