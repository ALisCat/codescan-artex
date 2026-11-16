package com.community.clinic.controller;

import com.community.clinic.common.ApiResponse;
import com.community.clinic.common.UserContext;
import com.community.clinic.service.SysConfigService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/admin")
public class SysConfigController {

    private final SysConfigService sysConfigService;

    public SysConfigController(SysConfigService sysConfigService) {
        this.sysConfigService = sysConfigService;
    }

    /**
     * POST /api/admin/config （仅管理员）
     * 请求 {"key":"...","value":"..."}
     */
    @PostMapping("/config")
    public ApiResponse<Void> save(@RequestBody Map<String, String> request) {
        String key = request.get("key");
        String value = request.get("value");
        sysConfigService.save(UserContext.require().getTenantId(), key, value);
        return ApiResponse.ok();
    }
}
