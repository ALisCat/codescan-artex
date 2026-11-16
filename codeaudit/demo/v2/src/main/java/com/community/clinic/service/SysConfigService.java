package com.community.clinic.service;

import com.community.clinic.common.BizException;
import com.community.clinic.mapper.SysConfigMapper;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

@Service
public class SysConfigService {

    private final SysConfigMapper sysConfigMapper;

    public SysConfigService(SysConfigMapper sysConfigMapper) {
        this.sysConfigMapper = sysConfigMapper;
    }

    public String get(Long tenantId, String key) {
        return sysConfigMapper.findValue(tenantId, key);
    }

    public String getOrDefault(Long tenantId, String key, String defaultValue) {
        String value = get(tenantId, key);
        return StringUtils.hasText(value) ? value : defaultValue;
    }

    public int getInt(Long tenantId, String key, int defaultValue) {
        String value = get(tenantId, key);
        if (!StringUtils.hasText(value)) {
            return defaultValue;
        }
        try {
            return Integer.parseInt(value.trim());
        } catch (NumberFormatException e) {
            return defaultValue;
        }
    }

    public String getRequired(Long tenantId, String key, String errorMsg) {
        String value = get(tenantId, key);
        if (!StringUtils.hasText(value)) {
            throw new BizException(errorMsg);
        }
        return value;
    }

    public void save(Long tenantId, String key, String value) {
        if (!StringUtils.hasText(key)) {
            throw new BizException(400, "配置项 key 不能为空");
        }
        sysConfigMapper.upsert(tenantId, key, value);
    }
}
