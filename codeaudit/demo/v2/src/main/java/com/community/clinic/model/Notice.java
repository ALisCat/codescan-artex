package com.community.clinic.model;

import lombok.Data;

@Data
public class Notice {
    private Long id;
    private String title;
    private String content;
    /** 发送渠道，目前只有 WEBHOOK */
    private String channel;
    private Long createdBy;
}
