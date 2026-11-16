package com.example.clinic.model;

import java.util.ArrayList;
import java.util.List;

public final class ClinicModels {

    private ClinicModels() {
    }

    public static class LoginUser {
        private Long userId;
        private String username;
        private String password;
        private String role;
        private String token;

        public Long getUserId() {
            return userId;
        }

        public void setUserId(Long userId) {
            this.userId = userId;
        }

        public String getUsername() {
            return username;
        }

        public void setUsername(String username) {
            this.username = username;
        }

        public String getPassword() {
            return password;
        }

        public void setPassword(String password) {
            this.password = password;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }

        public String getToken() {
            return token;
        }

        public void setToken(String token) {
            this.token = token;
        }
    }

    public static class LoginRequest {
        private String username;
        private String password;

        public String getUsername() {
            return username;
        }

        public void setUsername(String username) {
            this.username = username;
        }

        public String getPassword() {
            return password;
        }

        public void setPassword(String password) {
            this.password = password;
        }
    }

    public static class Patient {
        private Long id;
        private String name;
        private String phone;
        private String email;
        private String gender;
        private String birthDate;

        public Long getId() {
            return id;
        }

        public void setId(Long id) {
            this.id = id;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getPhone() {
            return phone;
        }

        public void setPhone(String phone) {
            this.phone = phone;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public String getGender() {
            return gender;
        }

        public void setGender(String gender) {
            this.gender = gender;
        }

        public String getBirthDate() {
            return birthDate;
        }

        public void setBirthDate(String birthDate) {
            this.birthDate = birthDate;
        }
    }

    public static class Appointment {
        private Long id;
        private Long patientId;
        private String patientName;
        private String appointmentDate;
        private String department;
        private String doctor;
        private String status;
        private String reason;

        public Long getId() {
            return id;
        }

        public void setId(Long id) {
            this.id = id;
        }

        public Long getPatientId() {
            return patientId;
        }

        public void setPatientId(Long patientId) {
            this.patientId = patientId;
        }

        public String getPatientName() {
            return patientName;
        }

        public void setPatientName(String patientName) {
            this.patientName = patientName;
        }

        public String getAppointmentDate() {
            return appointmentDate;
        }

        public void setAppointmentDate(String appointmentDate) {
            this.appointmentDate = appointmentDate;
        }

        public String getDepartment() {
            return department;
        }

        public void setDepartment(String department) {
            this.department = department;
        }

        public String getDoctor() {
            return doctor;
        }

        public void setDoctor(String doctor) {
            this.doctor = doctor;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public String getReason() {
            return reason;
        }

        public void setReason(String reason) {
            this.reason = reason;
        }
    }

    public static class Attachment {
        private Long id;
        private Long appointmentId;
        private String fileName;
        private String storedName;
        private String contentType;
        private Long fileSize;
        private String filePath;

        public Long getId() {
            return id;
        }

        public void setId(Long id) {
            this.id = id;
        }

        public Long getAppointmentId() {
            return appointmentId;
        }

        public void setAppointmentId(Long appointmentId) {
            this.appointmentId = appointmentId;
        }

        public String getFileName() {
            return fileName;
        }

        public void setFileName(String fileName) {
            this.fileName = fileName;
        }

        public String getStoredName() {
            return storedName;
        }

        public void setStoredName(String storedName) {
            this.storedName = storedName;
        }

        public String getContentType() {
            return contentType;
        }

        public void setContentType(String contentType) {
            this.contentType = contentType;
        }

        public Long getFileSize() {
            return fileSize;
        }

        public void setFileSize(Long fileSize) {
            this.fileSize = fileSize;
        }

        public String getFilePath() {
            return filePath;
        }

        public void setFilePath(String filePath) {
            this.filePath = filePath;
        }
    }

    public static class AppointmentDetail {
        private Appointment appointment;
        private Patient patient;
        private List<Attachment> attachments = new ArrayList<Attachment>();

        public Appointment getAppointment() {
            return appointment;
        }

        public void setAppointment(Appointment appointment) {
            this.appointment = appointment;
        }

        public Patient getPatient() {
            return patient;
        }

        public void setPatient(Patient patient) {
            this.patient = patient;
        }

        public List<Attachment> getAttachments() {
            return attachments;
        }

        public void setAttachments(List<Attachment> attachments) {
            this.attachments = attachments;
        }
    }

    public static class NoticeSendRequest {
        private Long patientId;
        private String channel;
        private String title;
        private String content;

        public Long getPatientId() {
            return patientId;
        }

        public void setPatientId(Long patientId) {
            this.patientId = patientId;
        }

        public String getChannel() {
            return channel;
        }

        public void setChannel(String channel) {
            this.channel = channel;
        }

        public String getTitle() {
            return title;
        }

        public void setTitle(String title) {
            this.title = title;
        }

        public String getContent() {
            return content;
        }

        public void setContent(String content) {
            this.content = content;
        }
    }

    public static class SysConfig {
        private String configKey;
        private String configValue;
        private String description;

        public String getConfigKey() {
            return configKey;
        }

        public void setConfigKey(String configKey) {
            this.configKey = configKey;
        }

        public String getConfigValue() {
            return configValue;
        }

        public void setConfigValue(String configValue) {
            this.configValue = configValue;
        }

        public String getDescription() {
            return description;
        }

        public void setDescription(String description) {
            this.description = description;
        }
    }
}
