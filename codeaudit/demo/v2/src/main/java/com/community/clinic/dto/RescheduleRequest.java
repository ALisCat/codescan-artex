package com.community.clinic.dto;

import lombok.Data;

@Data
public class RescheduleRequest {
    /** yyyy-MM-dd */
    private String regDate;
    /** 例如 09:00-10:00 */
    private String timeRange;
}
