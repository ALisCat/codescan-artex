package com.example.clinic.controller;

import com.example.clinic.model.ClinicModels.Attachment;
import com.example.clinic.service.ClinicService;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/file")
public class FileController {

    private final ClinicService clinicService;

    public FileController(ClinicService clinicService) {
        this.clinicService = clinicService;
    }

    @PostMapping("/upload")
    public Attachment upload(@RequestParam("file") MultipartFile file,
                             @RequestParam(value = "appointmentId", required = false) Long appointmentId) {
        return clinicService.saveAttachment(file, appointmentId);
    }

    @GetMapping("/download")
    public ResponseEntity<byte[]> download(@RequestParam("fileId") Long fileId) {
        Attachment attachment = clinicService.getAttachment(fileId);
        byte[] content = clinicService.readAttachment(attachment);

        MediaType contentType = MediaType.APPLICATION_OCTET_STREAM;
        if (attachment.getContentType() != null) {
            try {
                contentType = MediaType.parseMediaType(attachment.getContentType());
            } catch (IllegalArgumentException ignored) {
                contentType = MediaType.APPLICATION_OCTET_STREAM;
            }
        }

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(contentType);
        headers.set(HttpHeaders.CONTENT_DISPOSITION,
                "attachment; filename=\"" + attachment.getFileName() + "\"");
        return new ResponseEntity<byte[]>(content, headers, HttpStatus.OK);
    }
}
