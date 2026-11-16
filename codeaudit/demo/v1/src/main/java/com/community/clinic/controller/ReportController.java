package com.community.clinic.controller;

import com.community.clinic.service.ReportService;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.servlet.http.HttpServletResponse;
import java.io.IOException;

@RestController
@RequestMapping("/api/report")
public class ReportController {

    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    /**
     * GET /api/report/appointments?sort=reg_date&order=desc —— 返回 CSV，管理员使用。
     */
    @GetMapping("/appointments")
    public void appointments(@RequestParam(value = "sort", defaultValue = "reg_date") String sort,
                             @RequestParam(value = "order", defaultValue = "desc") String order,
                             HttpServletResponse response) throws IOException {
        String csv = reportService.buildCsv(sort, order);

        response.setCharacterEncoding("UTF-8");
        response.setContentType("text/csv;charset=UTF-8");
        response.setHeader(HttpHeaders.CONTENT_DISPOSITION, "attachment;filename=appointments.csv");
        response.getWriter().write("\uFEFF" + csv);
    }
}
