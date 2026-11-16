package com.community.clinic.service;

import com.community.clinic.common.BizException;
import com.community.clinic.common.LoginUser;
import com.community.clinic.common.UserContext;
import com.community.clinic.mapper.NoticeMapper;
import com.community.clinic.model.Notice;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import java.util.LinkedHashMap;
import java.util.Map;

@Service
public class NoticeService {

    private static final Logger log = LoggerFactory.getLogger(NoticeService.class);
    private static final String CHANNEL_WEBHOOK = "WEBHOOK";

    private final NoticeMapper noticeMapper;
    private final ObjectMapper objectMapper;
    private final RestTemplate restTemplate = new RestTemplate();

    public NoticeService(NoticeMapper noticeMapper, ObjectMapper objectMapper) {
        this.noticeMapper = noticeMapper;
        this.objectMapper = objectMapper;
    }

    /**
     * 通知群发：把 title/content POST 到公众号网关 webhook，并记录 notice 表。
     */
    public Long send(String title, String content, String webhook) {
        LoginUser user = UserContext.require();

        if (!StringUtils.hasText(title) || !StringUtils.hasText(content)) {
            throw new BizException(400, "title 与 content 不能为空");
        }
        if (!StringUtils.hasText(webhook)) {
            throw new BizException(400, "webhook 不能为空");
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("title", title);
        payload.put("content", content);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        try {
            String body = objectMapper.writeValueAsString(payload);
            restTemplate.postForEntity(webhook, new HttpEntity<>(body, headers), String.class);
        } catch (RestClientException e) {
            log.error("send notice to webhook failed, webhook={}", webhook, e);
            throw new BizException(502, "通知发送失败");
        } catch (Exception e) {
            throw new BizException(500, "通知内容序列化失败");
        }

        Notice notice = new Notice();
        notice.setTitle(title);
        notice.setContent(content);
        notice.setChannel(CHANNEL_WEBHOOK);
        notice.setCreatedBy(user.getId());
        noticeMapper.insert(notice);

        log.info("notice sent, id={}, webhook={}", notice.getId(), webhook);
        return notice.getId();
    }
}
