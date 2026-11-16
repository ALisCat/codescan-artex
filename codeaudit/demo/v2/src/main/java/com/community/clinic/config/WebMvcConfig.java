package com.community.clinic.config;

import com.community.clinic.interceptor.AuthInterceptor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebMvcConfig implements WebMvcConfigurer {

    private final AuthInterceptor authInterceptor;
    private final ClinicProperties clinicProperties;

    public WebMvcConfig(AuthInterceptor authInterceptor, ClinicProperties clinicProperties) {
        this.authInterceptor = authInterceptor;
        this.clinicProperties = clinicProperties;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(authInterceptor)
                .addPathPatterns("/api/**")
                .excludePathPatterns(clinicProperties.getAuth().getWhitelist());
    }
}
