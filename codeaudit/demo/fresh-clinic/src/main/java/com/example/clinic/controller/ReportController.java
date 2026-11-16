package com.example.clinic.controller;

import com.example.clinic.service.AppointmentService;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;

@RestController
@RequestMapping("/api/report")
public class ReportController {

    private final AppointmentService appointmentService;

    public ReportController(AppointmentService appointmentService) {
        this.appointmentService = appointmentService;
    }

    @GetMapping("/appointments")
    public ResponseEntity<String> appointments(
            @RequestParam(value = "sort", defaultValue = "appointmentDate") String sort,
            @RequestParam(value = "order", defaultValue = "asc") String order) {
        String csv = appointmentService.exportCsv(sort, order);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(new MediaType("text", "csv", StandardCharsets.UTF_8));
        headers.set(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"appointments.csv\"");
        return new ResponseEntity<String>(csv, headers, HttpStatus.OK);
    }
}
