package com.community.clinic.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Collections;
import java.util.Map;

@RestController
@RequestMapping("/api")
public class HealthController {

    /**
     * GET /api/health -> {"ok":true}
     */
    @GetMapping("/health")
    public Map<String, Object> health() {
        return Collections.<String, Object>singletonMap("ok", true);
    }
}
