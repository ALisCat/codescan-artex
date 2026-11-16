package com.community.clinic.controller;

import com.community.clinic.common.ApiResponse;
import com.community.clinic.service.FileService;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.nio.charset.StandardCharsets;
import java.util.Map;

@RestController
@RequestMapping("/api/file")
public class FileController {

    private final FileService fileService;

    public FileController(FileService fileService) {
        this.fileService = fileService;
    }

    /**
     * POST /api/file/upload （multipart: file, archiveId）
     */
    @PostMapping("/upload")
    public ApiResponse<Map<String, String>> upload(@RequestParam("file") MultipartFile file,
                                                   @RequestParam("archiveId") Long archiveId) {
        return ApiResponse.ok(fileService.upload(archiveId, file));
    }

    /**
     * GET /api/file/download?path=...
     */
    @GetMapping("/download")
    public ResponseEntity<byte[]> download(@RequestParam("path") String path) {
        FileService.DownloadFile file = fileService.download(path);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_OCTET_STREAM);
        headers.setContentDisposition(ContentDisposition.attachment()
                .filename(file.getFileName(), StandardCharsets.UTF_8)
                .build());
        return ResponseEntity.ok().headers(headers).body(file.getContent());
    }
}
