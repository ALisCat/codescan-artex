package com.example.clinic.controller;

import com.example.clinic.model.ClinicModels.SysConfig;
import com.example.clinic.service.ClinicService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/admin")
public class AdminController {

    private final ClinicService clinicService;

    public AdminController(ClinicService clinicService) {
        this.clinicService = clinicService;
    }

    @PostMapping("/config")
    public Map<String, Object> saveConfig(@RequestBody SysConfig config) {
        SysConfig saved = clinicService.saveConfig(config);

        Map<String, Object> response = new LinkedHashMap<String, Object>();
        response.put("configKey", saved.getConfigKey());
        response.put("configValue", saved.getConfigValue());
        response.put("saved", true);
        return response;
    }
}
