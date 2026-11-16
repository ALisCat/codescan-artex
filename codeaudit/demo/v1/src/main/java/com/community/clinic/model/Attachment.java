package com.community.clinic.model;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class Attachment {
    private Long id;
    private Long patientId;
    private String fileName;
    private String filePath;
    private LocalDateTime uploadTime;
}
