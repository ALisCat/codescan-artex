package com.community.clinic.controller;

import com.community.clinic.common.ApiResponse;
import com.community.clinic.common.LoginUser;
import com.community.clinic.dto.LoginRequest;
import com.community.clinic.service.AuthService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    /**
     * POST /api/auth/login
     * 请求 {"phone":"...","password":"..."}，返回 {"token":"...","role":"..."}
     */
    @PostMapping("/login")
    public ApiResponse<Map<String, Object>> login(@RequestBody LoginRequest request) {
        LoginUser user = authService.login(request.getPhone(), request.getPassword());
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("token", user.getToken());
        data.put("role", user.getRole());
        return ApiResponse.ok(data);
    }
}
