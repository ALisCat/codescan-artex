package com.example.clinic.controller;

import com.example.clinic.model.ClinicModels.Appointment;
import com.example.clinic.model.ClinicModels.AppointmentDetail;
import com.example.clinic.service.AppointmentService;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/appointment")
public class AppointmentController {

    private final AppointmentService appointmentService;

    public AppointmentController(AppointmentService appointmentService) {
        this.appointmentService = appointmentService;
    }

    @GetMapping("/{id}")
    public AppointmentDetail detail(@PathVariable("id") Long id) {
        return appointmentService.getDetail(id);
    }

    @GetMapping("/list")
    public List<Appointment> list(@RequestParam(value = "patientId", required = false) Long patientId,
                                  @RequestParam(value = "status", required = false) String status,
                                  @RequestParam(value = "doctor", required = false) String doctor) {
        return appointmentService.list(patientId, status, doctor);
    }

    @PostMapping("/cancel")
    public Map<String, Object> cancel(@RequestBody Map<String, Object> body) {
        Long appointmentId = toLong(body.get("appointmentId"), body.get("id"));
        String reason = body.get("reason") == null ? null : String.valueOf(body.get("reason"));
        int updated = appointmentService.cancel(appointmentId, reason);

        Map<String, Object> response = new LinkedHashMap<String, Object>();
        response.put("appointmentId", appointmentId);
        response.put("cancelled", updated > 0);
        return response;
    }

    @PostMapping("/{id}/reschedule")
    public Map<String, Object> reschedule(@PathVariable("id") Long id,
                                          @RequestBody Map<String, Object> body) {
        String appointmentDate = body.get("appointmentDate") == null
                ? null : String.valueOf(body.get("appointmentDate"));
        String doctor = body.get("doctor") == null ? null : String.valueOf(body.get("doctor"));
        int updated = appointmentService.reschedule(id, appointmentDate, doctor);

        Map<String, Object> response = new LinkedHashMap<String, Object>();
        response.put("appointmentId", id);
        response.put("rescheduled", updated > 0);
        response.put("appointmentDate", appointmentDate);
        response.put("doctor", doctor);
        return response;
    }

    private Long toLong(Object primary, Object fallback) {
        Object value = primary == null ? fallback : primary;
        if (value == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "appointmentId is required");
        }
        try {
            return Long.valueOf(String.valueOf(value));
        } catch (NumberFormatException ex) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "appointmentId is invalid", ex);
        }
    }
}
