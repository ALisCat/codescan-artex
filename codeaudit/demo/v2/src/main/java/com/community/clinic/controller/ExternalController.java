package com.community.clinic.controller;

import com.community.clinic.common.ApiResponse;
import com.community.clinic.service.ExternalService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/external")
public class ExternalController {

    private final ExternalService externalService;

    public ExternalController(ExternalService externalService) {
        this.externalService = externalService;
    }

    /**
     * GET /api/external/patient-card?archiveId=1
     */
    @GetMapping("/patient-card")
    public ApiResponse<Object> patientCard(@RequestParam("archiveId") Long archiveId) {
        return ApiResponse.ok(externalService.patientCards(archiveId));
    }
}
