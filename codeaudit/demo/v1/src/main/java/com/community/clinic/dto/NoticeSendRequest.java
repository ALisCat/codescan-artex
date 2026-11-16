package com.community.clinic.dto;

import lombok.Data;

@Data
public class NoticeSendRequest {
    private String title;
    private String content;
    private String webhook;
}
