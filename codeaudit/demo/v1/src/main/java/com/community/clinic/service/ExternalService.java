package com.community.clinic.service;

import com.community.clinic.common.BizException;
import com.community.clinic.common.LoginUser;
import com.community.clinic.common.UserContext;
import com.community.clinic.mapper.ArchiveMapper;
import com.community.clinic.model.Archive;
import com.community.clinic.util.HisClient;
import org.springframework.stereotype.Service;

import java.util.Objects;

@Service
public class ExternalService {

    private final ArchiveMapper archiveMapper;
    private final HisClient hisClient;

    public ExternalService(ArchiveMapper archiveMapper, HisClient hisClient) {
        this.archiveMapper = archiveMapper;
        this.hisClient = hisClient;
    }

    /**
     * 调用 HIS 的 patientCard 接口，返回档案下的就诊卡列表。
     */
    public Object patientCards(Long archiveId) {
        LoginUser user = UserContext.require();
        if (archiveId == null) {
            throw new BizException(400, "archiveId 不能为空");
        }

        Archive archive = archiveMapper.findById(archiveId, user.getTenantId());
        if (archive == null) {
            throw new BizException(404, "档案不存在");
        }
        if ("PATIENT".equals(user.getRole()) && !Objects.equals(archive.getPatientId(), user.getId())) {
            throw new BizException(403, "无权查看他人的档案");
        }

        return hisClient.patientCards(archiveId, user.getTenantId());
    }
}
