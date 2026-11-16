package com.community.clinic.service;

import com.community.clinic.common.BizException;
import com.community.clinic.common.LoginUser;
import com.community.clinic.common.UserContext;
import com.community.clinic.config.ClinicProperties;
import com.community.clinic.mapper.ArchiveMapper;
import com.community.clinic.mapper.AttachmentMapper;
import com.community.clinic.model.Archive;
import com.community.clinic.model.Attachment;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

@Service
public class FileService {

    private final ClinicProperties clinicProperties;
    private final ArchiveMapper archiveMapper;
    private final AttachmentMapper attachmentMapper;

    public FileService(ClinicProperties clinicProperties,
                       ArchiveMapper archiveMapper,
                       AttachmentMapper attachmentMapper) {
        this.clinicProperties = clinicProperties;
        this.archiveMapper = archiveMapper;
        this.attachmentMapper = attachmentMapper;
    }

    /**
     * 上传到 /data/clinic/upload/&lt;archiveId&gt;/ 下，单文件不超过 10MB。
     */
    public Map<String, String> upload(Long archiveId, MultipartFile file) {
        LoginUser user = UserContext.require();

        if (archiveId == null) {
            throw new BizException(400, "archiveId 不能为空");
        }
        if (file == null || file.isEmpty()) {
            throw new BizException(400, "请选择要上传的文件");
        }
        if (file.getSize() > clinicProperties.getMaxFileSize()) {
            throw new BizException(400, "文件大小不能超过10MB");
        }

        Archive archive = archiveMapper.findById(archiveId, user.getTenantId());
        if (archive == null) {
            throw new BizException(404, "档案不存在");
        }
        if ("PATIENT".equals(user.getRole()) && !Objects.equals(archive.getPatientId(), user.getId())) {
            throw new BizException(403, "无权操作他人的档案");
        }

        String originalName = file.getOriginalFilename() == null ? "file" : file.getOriginalFilename();
        String storedName = originalName;

        Path dir = Paths.get(clinicProperties.getUploadDir(), String.valueOf(archiveId));
        Path target = dir.resolve(storedName);
        try {
            Files.createDirectories(dir);
            file.transferTo(target.toFile());
        } catch (IOException e) {
            throw new BizException(500, "文件保存失败: " + e.getMessage());
        }

        Attachment attachment = new Attachment();
        attachment.setPatientId(archive.getPatientId());
        attachment.setFileName(originalName);
        attachment.setFilePath(archiveId + "/" + storedName);
        attachment.setUploadTime(LocalDateTime.now());
        attachmentMapper.insert(attachment);

        Map<String, String> result = new LinkedHashMap<>();
        result.put("fileName", originalName);
        result.put("path", archiveId + "/" + storedName);
        return result;
    }

    /**
     * 按相对路径读取上传目录下的文件（患者只能下载自己档案下的附件）。
     */
    public DownloadFile download(String path) {
        LoginUser user = UserContext.require();
        if (!StringUtils.hasText(path)) {
            throw new BizException(400, "path 不能为空");
        }

        Path target = Paths.get(path);
        if (!Files.isRegularFile(target)) {
            throw new BizException(404, "文件不存在");
        }

        try {
            return new DownloadFile(Files.readAllBytes(target), target.getFileName().toString());
        } catch (IOException e) {
            throw new BizException(500, "文件读取失败: " + e.getMessage());
        }
    }

    public static class DownloadFile {
        private final byte[] content;
        private final String fileName;

        public DownloadFile(byte[] content, String fileName) {
            this.content = content;
            this.fileName = fileName;
        }

        public byte[] getContent() {
            return content;
        }

        public String getFileName() {
            return fileName;
        }
    }
}
