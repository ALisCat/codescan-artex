package com.example.clinic.controller;

import com.example.clinic.context.UserContext;
import com.example.clinic.model.ClinicModels.NoticeSendRequest;
import com.example.clinic.service.ClinicService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/notice")
public class NoticeController {

    private final ClinicService clinicService;

    public NoticeController(ClinicService clinicService) {
        this.clinicService = clinicService;
    }

    @PostMapping("/send")
    public Map<String, Object> send(@RequestBody NoticeSendRequest request) {
        int saved = clinicService.sendNotice(request, UserContext.get());

        Map<String, Object> response = new LinkedHashMap<String, Object>();
        response.put("patientId", request.getPatientId());
        response.put("channel", request.getChannel());
        response.put("sent", saved > 0);
        return response;
    }
}
