package com.example.clinic.controller;

import com.example.clinic.model.ClinicModels.LoginRequest;
import com.example.clinic.model.ClinicModels.LoginUser;
import com.example.clinic.service.ClinicService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final ClinicService clinicService;

    public AuthController(ClinicService clinicService) {
        this.clinicService = clinicService;
    }

    @PostMapping("/login")
    public ResponseEntity<Map<String, Object>> login(@RequestBody LoginRequest request) {
        if (request == null) {
            return ResponseEntity.badRequest().build();
        }

        LoginUser user = clinicService.login(request.getUsername(), request.getPassword());
        if (user == null) {
            Map<String, Object> error = new LinkedHashMap<String, Object>();
            error.put("error", "Invalid username or password");
            return new ResponseEntity<Map<String, Object>>(error, HttpStatus.UNAUTHORIZED);
        }

        Map<String, Object> response = new LinkedHashMap<String, Object>();
        response.put("token", user.getToken());
        response.put("userId", user.getUserId());
        response.put("username", user.getUsername());
        response.put("role", user.getRole());
        return ResponseEntity.ok(response);
    }
}
