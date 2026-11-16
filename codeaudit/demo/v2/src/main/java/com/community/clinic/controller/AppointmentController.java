package com.community.clinic.controller;

import com.community.clinic.common.ApiResponse;
import com.community.clinic.common.BizException;
import com.community.clinic.dto.CancelRequest;
import com.community.clinic.dto.RescheduleRequest;
import com.community.clinic.model.AppointmentDetail;
import com.community.clinic.service.AppointmentService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/appointment")
public class AppointmentController {

    private final AppointmentService appointmentService;

    public AppointmentController(AppointmentService appointmentService) {
        this.appointmentService = appointmentService;
    }

    /**
     * GET /api/appointment/{id}
     */
    @GetMapping("/{id}")
    public ApiResponse<AppointmentDetail> detail(@PathVariable("id") Long id) {
        return ApiResponse.ok(appointmentService.detail(id));
    }

    /**
     * GET /api/appointment/list
     */
    @GetMapping("/list")
    public ApiResponse<Map<String, Object>> list(@RequestParam(value = "status", required = false) String status,
                                                 @RequestParam(value = "beginDate", required = false) String beginDate,
                                                 @RequestParam(value = "endDate", required = false) String endDate,
                                                 @RequestParam(value = "page", defaultValue = "1") Integer page,
                                                 @RequestParam(value = "pageSize", defaultValue = "10") Integer pageSize) {
        return ApiResponse.ok(appointmentService.list(status, beginDate, endDate, page, pageSize));
    }

    /**
     * POST /api/appointment/cancel
     */
    @PostMapping("/cancel")
    public ApiResponse<Void> cancel(@RequestBody CancelRequest request) {
        if (request == null || request.getAppointmentId() == null) {
            throw new BizException(400, "appointmentId 不能为空");
        }
        appointmentService.cancel(request.getAppointmentId());
        return ApiResponse.ok();
    }

    /**
     * POST /api/appointment/{id}/reschedule
     */
    @PostMapping("/{id}/reschedule")
    public ApiResponse<Void> reschedule(@PathVariable("id") Long id,
                                        @RequestBody RescheduleRequest request) {
        appointmentService.reschedule(id, request);
        return ApiResponse.ok();
    }
}
