package com.community.clinic.interceptor;

import com.community.clinic.common.BizException;
import com.community.clinic.common.LoginUser;
import com.community.clinic.common.UserContext;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;
import org.springframework.util.AntPathMatcher;
import org.springframework.util.StringUtils;
import org.springframework.web.servlet.HandlerInterceptor;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

/**
 * 登录校验 + 角色校验：从 token 请求头取用户，token 存在 Redis 的 clinic:token:&lt;token&gt; 下。
 */
@Component
public class AuthInterceptor implements HandlerInterceptor {

    public static final String TOKEN_KEY_PREFIX = "clinic:token:";

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final AntPathMatcher pathMatcher = new AntPathMatcher();

    public AuthInterceptor(StringRedisTemplate redisTemplate, ObjectMapper objectMapper) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        String token = request.getHeader("token");
        if (!StringUtils.hasText(token)) {
            throw new BizException(401, "未登录");
        }

        String json = redisTemplate.opsForValue().get(TOKEN_KEY_PREFIX + token);
        if (!StringUtils.hasText(json)) {
            throw new BizException(401, "登录已失效，请重新登录");
        }

        LoginUser user;
        try {
            user = objectMapper.readValue(json, LoginUser.class);
        } catch (Exception e) {
            throw new BizException(401, "登录信息异常，请重新登录");
        }
        user.setToken(token);
        UserContext.set(user);

        if (needAdmin(request.getRequestURI()) && !"ADMIN".equals(user.getRole())) {
            throw new BizException(403, "无权访问");
        }
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response, Object handler, Exception ex) {
        UserContext.clear();
    }

    private boolean needAdmin(String uri) {
        return pathMatcher.match("/api/admin/**", uri)
                || pathMatcher.match("/api/report/**", uri)
                || pathMatcher.match("/api/notice/**", uri);
    }
}
