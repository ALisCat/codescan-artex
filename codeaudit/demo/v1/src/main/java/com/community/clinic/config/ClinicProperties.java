package com.community.clinic.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * clinic.* 配置（上传目录、免登录白名单）。
 */
@Data
@Component
@ConfigurationProperties(prefix = "clinic")
public class ClinicProperties {

    /** 附件根目录 */
    private String uploadDir = "/data/clinic/upload";

    /** 单文件大小上限（字节），默认 10MB */
    private long maxFileSize = 10 * 1024 * 1024;

    private Auth auth = new Auth();

    @Data
    public static class Auth {
        /** 拦截器白名单，支持 Ant 风格 */
        private List<String> whitelist = new ArrayList<>();
    }
}
