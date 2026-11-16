package com.community.clinic.controller;

import com.community.clinic.common.ApiResponse;
import com.community.clinic.dto.NoticeSendRequest;
import com.community.clinic.service.NoticeService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/notice")
public class NoticeController {

    private final NoticeService noticeService;

    public NoticeController(NoticeService noticeService) {
        this.noticeService = noticeService;
    }

    /**
     * POST /api/notice/send
     */
    @PostMapping("/send")
    public ApiResponse<Map<String, Object>> send(@RequestBody NoticeSendRequest request) {
        Long id = noticeService.send(request.getTitle(), request.getContent(), request.getWebhook());
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("noticeId", id);
        return ApiResponse.ok(data);
    }
}
