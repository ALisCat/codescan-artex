package com.community.clinic.service;

import com.community.clinic.common.BizException;
import com.community.clinic.common.LoginUser;
import com.community.clinic.common.UserContext;
import com.community.clinic.dto.RescheduleRequest;
import com.community.clinic.mapper.AppointmentMapper;
import com.community.clinic.model.Appointment;
import com.community.clinic.model.AppointmentDetail;
import com.community.clinic.util.HisClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

@Service
public class AppointmentService {

    public static final String STATUS_PENDING = "PENDING";
    public static final String STATUS_CANCELLED = "CANCELLED";

    private final AppointmentMapper appointmentMapper;
    private final SysConfigService sysConfigService;
    private final HisClient hisClient;

    public AppointmentService(AppointmentMapper appointmentMapper,
                              SysConfigService sysConfigService,
                              HisClient hisClient) {
        this.appointmentMapper = appointmentMapper;
        this.sysConfigService = sysConfigService;
        this.hisClient = hisClient;
    }

    public AppointmentDetail detail(Long id) {
        LoginUser user = UserContext.require();
        AppointmentDetail detail = appointmentMapper.findDetail(id, user.getTenantId());
        if (detail == null) {
            throw new BizException(404, "预约不存在");
        }
        checkOwner(detail.getPatientId(), user);
        return detail;
    }

    /**
     * 当前患者的预约列表（分页）。
     */
    public Map<String, Object> list(String status, String beginDate, String endDate, Integer page, Integer pageSize) {
        LoginUser user = UserContext.require();
        if (!"PATIENT".equals(user.getRole())) {
            throw new BizException(403, "仅患者可查看自己的预约列表");
        }

        int pageNo = (page == null || page < 1) ? 1 : page;
        int size = (pageSize == null || pageSize < 1) ? 10 : Math.min(pageSize, 100);
        LocalDate begin = parseDate(beginDate, "beginDate");
        LocalDate end = parseDate(endDate, "endDate");

        long total = appointmentMapper.countByPatient(user.getId(), user.getTenantId(), status, begin, end);
        List<Appointment> list = appointmentMapper.pageByPatient(
                user.getId(), user.getTenantId(), status, begin, end, (pageNo - 1) * size, size);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("total", total);
        result.put("page", pageNo);
        result.put("pageSize", size);
        result.put("list", list);
        return result;
    }

    /**
     * 取消预约：仅“待就诊”可取消，更新状态为已取消并调用 HIS 退款。
     */
    @Transactional
    public void cancel(Long appointmentId) {
        LoginUser user = UserContext.require();
        Appointment appointment = appointmentMapper.findById(appointmentId, user.getTenantId());
        if (appointment == null) {
            throw new BizException(404, "预约不存在");
        }
        checkOwner(appointment.getPatientId(), user);

        if (!STATUS_PENDING.equals(appointment.getStatus())) {
            throw new BizException(400, "仅“待就诊”的预约可取消");
        }

        appointmentMapper.updateStatus(appointment.getId(), STATUS_CANCELLED);
        hisClient.refund(appointment.getId(), appointment.getFee(), user.getTenantId());
    }

    /**
     * 改约：校验目标时段号源后更新预约时间。
     */
    @Transactional
    public void reschedule(Long id, RescheduleRequest request) {
        LoginUser user = UserContext.require();
        if (request == null || !StringUtils.hasText(request.getRegDate())
                || !StringUtils.hasText(request.getTimeRange())) {
            throw new BizException(400, "regDate 与 timeRange 不能为空");
        }

        Appointment appointment = appointmentMapper.findById(id, user.getTenantId());
        if (appointment == null) {
            throw new BizException(404, "预约不存在");
        }
        checkOwner(appointment.getPatientId(), user);

        if (STATUS_CANCELLED.equals(appointment.getStatus())) {
            throw new BizException(400, "已取消的预约不能改约");
        }

        LocalDate regDate = parseDate(request.getRegDate(), "regDate");
        String timeRange = request.getTimeRange().trim();

        int capacity = sysConfigService.getInt(user.getTenantId(), "appointment.capacity", 20);
        int used = appointmentMapper.countSlot(appointment.getDoctorId(), regDate, timeRange);
        if (used >= capacity) {
            throw new BizException(400, "该时段号源已满，请选择其他时段");
        }

        appointmentMapper.updateSchedule(appointment.getId(), regDate, timeRange);
    }

    private void checkOwner(Long patientId, LoginUser user) {
        if ("PATIENT".equals(user.getRole()) && !Objects.equals(patientId, user.getId())) {
            throw new BizException(403, "无权操作他人的预约");
        }
    }

    private LocalDate parseDate(String value, String fieldName) {
        if (!StringUtils.hasText(value)) {
            return null;
        }
        try {
            return LocalDate.parse(value.trim());
        } catch (DateTimeParseException e) {
            throw new BizException(400, fieldName + " 日期格式错误，应为 yyyy-MM-dd");
        }
    }
}
