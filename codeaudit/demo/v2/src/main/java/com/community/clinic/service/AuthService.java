package com.community.clinic.service;

import com.community.clinic.common.BizException;
import com.community.clinic.common.LoginUser;
import com.community.clinic.mapper.PatientMapper;
import com.community.clinic.mapper.SysUserMapper;
import com.community.clinic.model.Patient;
import com.community.clinic.model.SysUser;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.Duration;
import java.util.UUID;

import static com.community.clinic.interceptor.AuthInterceptor.TOKEN_KEY_PREFIX;

@Service
public class AuthService {

    /** token 有效期 24 小时 */
    private static final Duration TOKEN_TTL = Duration.ofHours(24);

    private final PatientMapper patientMapper;
    private final SysUserMapper sysUserMapper;
    private final PasswordEncoder passwordEncoder;
    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;

    public AuthService(PatientMapper patientMapper,
                       SysUserMapper sysUserMapper,
                       PasswordEncoder passwordEncoder,
                       StringRedisTemplate redisTemplate,
                       ObjectMapper objectMapper) {
        this.patientMapper = patientMapper;
        this.sysUserMapper = sysUserMapper;
        this.passwordEncoder = passwordEncoder;
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
    }

    /**
     * 手机号 + 密码登录：先查患者，再查医生/管理员账号。
     * 成功后生成 token，用户信息写入 Redis 的 clinic:token:&lt;token&gt;。
     */
    public LoginUser login(String phone, String password) {
        if (!StringUtils.hasText(phone) || !StringUtils.hasText(password)) {
            throw new BizException(400, "手机号和密码不能为空");
        }

        LoginUser user = loginAsPatient(phone, password);
        if (user == null) {
            user = loginAsStaff(phone, password);
        }
        if (user == null) {
            throw new BizException(401, "手机号或密码错误");
        }

        String token = UUID.randomUUID().toString().replace("-", "");
        user.setToken(token);
        try {
            redisTemplate.opsForValue()
                    .set(TOKEN_KEY_PREFIX + token, objectMapper.writeValueAsString(user), TOKEN_TTL);
        } catch (Exception e) {
            throw new BizException(500, "登录信息写入失败");
        }
        return user;
    }

    private LoginUser loginAsPatient(String phone, String password) {
        Patient patient = patientMapper.findByPhone(phone);
        if (patient == null || !matches(password, patient.getPassword())) {
            return null;
        }
        return buildUser(patient.getId(), patient.getName(), patient.getPhone(), "PATIENT", patient.getTenantId());
    }

    private LoginUser loginAsStaff(String phone, String password) {
        SysUser staff = sysUserMapper.findByPhone(phone);
        if (staff == null || !matches(password, staff.getPassword())) {
            return null;
        }
        return buildUser(staff.getId(), staff.getName(), staff.getPhone(), staff.getRole(), staff.getTenantId());
    }

    private boolean matches(String raw, String encoded) {
        if (!StringUtils.hasText(encoded)) {
            return false;
        }
        return passwordEncoder.matches(raw, encoded);
    }

    private LoginUser buildUser(Long id, String name, String phone, String role, Long tenantId) {
        LoginUser user = new LoginUser();
        user.setId(id);
        user.setName(name);
        user.setPhone(phone);
        user.setRole(role);
        user.setTenantId(tenantId == null ? 1L : tenantId);
        return user;
    }
}
