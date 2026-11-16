package com.example.clinic.service;

import com.example.clinic.mapper.AppointmentMapper;
import com.example.clinic.mapper.ClinicMapper;
import com.example.clinic.model.ClinicModels.Appointment;
import com.example.clinic.model.ClinicModels.AppointmentDetail;
import com.example.clinic.model.ClinicModels.Patient;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class AppointmentService {

    private static final Map<String, String> SORT_COLUMNS = new HashMap<String, String>();

    static {
        SORT_COLUMNS.put("id", "a.id");
        SORT_COLUMNS.put("patientName", "p.name");
        SORT_COLUMNS.put("appointmentDate", "a.appointment_date");
        SORT_COLUMNS.put("department", "a.department");
        SORT_COLUMNS.put("doctor", "a.doctor");
        SORT_COLUMNS.put("status", "a.status");
    }

    private final AppointmentMapper appointmentMapper;
    private final ClinicMapper clinicMapper;

    public AppointmentService(AppointmentMapper appointmentMapper, ClinicMapper clinicMapper) {
        this.appointmentMapper = appointmentMapper;
        this.clinicMapper = clinicMapper;
    }

    public AppointmentDetail getDetail(Long id) {
        Appointment appointment = appointmentMapper.findById(id);
        if (appointment == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Appointment not found");
        }

        AppointmentDetail detail = new AppointmentDetail();
        detail.setAppointment(appointment);
        Patient patient = clinicMapper.findPatientById(appointment.getPatientId());
        detail.setPatient(patient);
        detail.setAttachments(clinicMapper.findAttachmentsByAppointmentId(id));
        return detail;
    }

    public List<Appointment> list(Long patientId, String status, String doctor) {
        return appointmentMapper.findList(patientId, status, doctor);
    }

    public int cancel(Long id, String reason) {
        return appointmentMapper.cancel(id, reason);
    }

    public int reschedule(Long id, String appointmentDate, String doctor) {
        if (appointmentDate == null || appointmentDate.trim().isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "appointmentDate is required");
        }
        return appointmentMapper.reschedule(id, appointmentDate, doctor);
    }

    public String exportCsv(String sort, String order) {
        String column = SORT_COLUMNS.get(sort == null ? "appointmentDate" : sort);
        if (column == null) {
            column = SORT_COLUMNS.get("appointmentDate");
        }
        String direction = "desc".equalsIgnoreCase(order) ? "DESC" : "ASC";

        StringBuilder csv = new StringBuilder();
        csv.append("id,patientId,patientName,appointmentDate,department,doctor,status,reason\n");
        for (Appointment appointment : appointmentMapper.findForReport(column, direction)) {
            append(csv, appointment.getId());
            csv.append(',');
            append(csv, appointment.getPatientId());
            csv.append(',');
            append(csv, appointment.getPatientName());
            csv.append(',');
            append(csv, appointment.getAppointmentDate());
            csv.append(',');
            append(csv, appointment.getDepartment());
            csv.append(',');
            append(csv, appointment.getDoctor());
            csv.append(',');
            append(csv, appointment.getStatus());
            csv.append(',');
            append(csv, appointment.getReason());
            csv.append('\n');
        }
        return csv.toString();
    }

    private void append(StringBuilder csv, Object value) {
        if (value == null) {
            return;
        }
        csv.append('"').append(String.valueOf(value).replace("\"", "\"\"")).append('"');
    }
}
