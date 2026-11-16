package com.example.clinic.interceptor;

import com.example.clinic.context.UserContext;
import com.example.clinic.model.ClinicModels.LoginUser;
import com.example.clinic.service.ClinicService;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.IOException;

@Component
public class AuthInterceptor implements HandlerInterceptor {

    private final ClinicService clinicService;

    public AuthInterceptor(ClinicService clinicService) {
        this.clinicService = clinicService;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler)
            throws IOException {
        if ("OPTIONS".equalsIgnoreCase(request.getMethod())) {
            return true;
        }

        String token = readToken(request);
        LoginUser user = clinicService.resolveToken(token);
        if (user == null) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write("{\"error\":\"Unauthorized\"}");
            return false;
        }

        UserContext.set(user);
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response, Object handler,
                                Exception ex) {
        UserContext.clear();
    }

    private String readToken(HttpServletRequest request) {
        String token = request.getHeader("X-Auth-Token");
        if (isBlank(token)) {
            token = request.getHeader("token");
        }
        if (isBlank(token)) {
            token = request.getHeader("Authorization");
        }
        if (!isBlank(token) && token.startsWith("Bearer ")) {
            token = token.substring(7);
        }
        return token == null ? null : token.trim();
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }
}
