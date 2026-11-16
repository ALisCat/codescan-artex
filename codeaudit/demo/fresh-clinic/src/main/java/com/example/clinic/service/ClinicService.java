package com.example.clinic.service;

import com.example.clinic.mapper.ClinicMapper;
import com.example.clinic.model.ClinicModels.Attachment;
import com.example.clinic.model.ClinicModels.LoginUser;
import com.example.clinic.model.ClinicModels.NoticeSendRequest;
import com.example.clinic.model.ClinicModels.Patient;
import com.example.clinic.model.ClinicModels.SysConfig;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class ClinicService {

    private final ClinicMapper clinicMapper;
    private final Map<String, LoginUser> sessions = new ConcurrentHashMap<String, LoginUser>();
    private final Path uploadDirectory = Paths.get("uploads").toAbsolutePath().normalize();

    public ClinicService(ClinicMapper clinicMapper) {
        this.clinicMapper = clinicMapper;
    }

    public LoginUser login(String username, String password) {
        if (username == null || password == null) {
            return null;
        }

        LoginUser user = clinicMapper.findLoginUser(username);
        if (user == null || !password.equals(user.getPassword())) {
            return null;
        }

        String token = UUID.randomUUID().toString().replace("-", "");
        user.setPassword(null);
        user.setToken(token);
        sessions.put(token, user);
        return user;
    }

    public LoginUser resolveToken(String token) {
        if (token == null || token.trim().isEmpty()) {
            return null;
        }
        return sessions.get(token);
    }

    public Attachment saveAttachment(MultipartFile file, Long appointmentId) {
        if (file == null || file.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "File is required");
        }

        try {
            Files.createDirectories(uploadDirectory);
            String originalName = file.getOriginalFilename();
            if (originalName == null || originalName.trim().isEmpty()) {
                originalName = "upload.bin";
            }
            originalName = Paths.get(originalName).getFileName().toString();
            String storedName = UUID.randomUUID().toString().replace("-", "") + "-" + originalName;
            Path target = uploadDirectory.resolve(storedName).normalize();
            Files.copy(file.getInputStream(), target, StandardCopyOption.REPLACE_EXISTING);

            Attachment attachment = new Attachment();
            attachment.setAppointmentId(appointmentId);
            attachment.setFileName(originalName);
            attachment.setStoredName(storedName);
            attachment.setContentType(file.getContentType());
            attachment.setFileSize(file.getSize());
            attachment.setFilePath(target.toString());
            clinicMapper.insertAttachment(attachment);
            return attachment;
        } catch (IOException ex) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Unable to store file", ex);
        }
    }

    public Attachment getAttachment(Long id) {
        Attachment attachment = clinicMapper.findAttachmentById(id);
        if (attachment == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Attachment not found");
        }
        return attachment;
    }

    public byte[] readAttachment(Attachment attachment) {
        try {
            return Files.readAllBytes(Paths.get(attachment.getFilePath()));
        } catch (IOException ex) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Attachment content not found", ex);
        }
    }

    public int sendNotice(NoticeSendRequest request, LoginUser user) {
        if (request == null || request.getPatientId() == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "patientId is required");
        }
        Patient patient = clinicMapper.findPatientById(request.getPatientId());
        if (patient == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Patient not found");
        }
        return clinicMapper.insertNotice(
                request.getPatientId(),
                request.getChannel(),
                request.getTitle(),
                request.getContent(),
                user == null ? null : user.getUserId());
    }

    public SysConfig getConfig(String configKey) {
        return clinicMapper.findConfig(configKey);
    }

    public SysConfig saveConfig(SysConfig config) {
        if (config == null || config.getConfigKey() == null || config.getConfigKey().trim().isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "configKey is required");
        }
        clinicMapper.upsertConfig(config);
        return config;
    }
}
