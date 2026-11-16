package com.community.clinic.util;

import com.community.clinic.common.BizException;
import com.community.clinic.service.SysConfigService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * HIS（院内系统）对接工具类：HTTP + JSON。
 * HIS 地址从 sys_config 的 his.base_url 读取。
 */
@Component
public class HisClient {

    private static final Logger log = LoggerFactory.getLogger(HisClient.class);

    private static final String BASE_URL_KEY = "his.base_url";

    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;
    private final SysConfigService sysConfigService;

    public HisClient(ObjectMapper objectMapper, SysConfigService sysConfigService) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(5000);
        factory.setReadTimeout(5000);
        this.restTemplate = new RestTemplate(factory);
        this.objectMapper = objectMapper;
        this.sysConfigService = sysConfigService;
    }

    /**
     * 取消预约后调用 HIS 退款接口。
     */
    public void refund(Long appointmentId, BigDecimal fee, Long tenantId) {
        String url = baseUrl(tenantId) + "/refund";
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("appointmentId", appointmentId);
        body.put("fee", fee);

        String response;
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            response = restTemplate.postForObject(url, new HttpEntity<>(toJson(body), headers), String.class);
        } catch (RestClientException e) {
            log.error("call his refund failed, appointmentId={}", appointmentId, e);
            throw new BizException(502, "HIS 退款接口调用失败");
        }
        log.info("his refund response, appointmentId={}, response={}", appointmentId, response);
        checkHisResponse(response, "退款");
    }

    /**
     * 查询档案下的就诊卡列表。
     */
    public Object patientCards(Long archiveId, Long tenantId) {
        String url = baseUrl(tenantId) + "/patientCard?archiveId=" + archiveId;
        String response;
        try {
            response = restTemplate.getForObject(url, String.class);
        } catch (RestClientException e) {
            log.error("call his patientCard failed, archiveId={}", archiveId, e);
            throw new BizException(502, "HIS 就诊卡接口调用失败");
        }

        JsonNode root = readTree(response);
        if (root != null && root.has("code") && root.get("code").asInt() != 0) {
            throw new BizException(502, "HIS 就诊卡接口返回失败: " + root.path("msg").asText(""));
        }
        if (root != null && root.has("data")) {
            return root.get("data");
        }
        return root;
    }

    private void checkHisResponse(String response, String action) {
        JsonNode root = readTree(response);
        if (root != null && root.has("code") && root.get("code").asInt() != 0) {
            throw new BizException(502, "HIS " + action + "失败: " + root.path("msg").asText(""));
        }
    }

    private JsonNode readTree(String response) {
        if (!StringUtils.hasText(response)) {
            return null;
        }
        try {
            return objectMapper.readTree(response);
        } catch (Exception e) {
            log.warn("his response is not json: {}", response);
            return null;
        }
    }

    private String baseUrl(Long tenantId) {
        String baseUrl = sysConfigService.getRequired(tenantId, BASE_URL_KEY, "未配置 HIS 地址（his.base_url）");
        return baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception e) {
            throw new BizException(500, "请求 HIS 时序列化失败");
        }
    }
}
