package com.community.clinic.mapper;

import com.community.clinic.model.Appointment;
import com.community.clinic.model.AppointmentDetail;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

/**
 * 预约相关 SQL 全部在 mapper/AppointmentMapper.xml。
 */
@Mapper
public interface AppointmentMapper {

    AppointmentDetail findDetail(@Param("id") Long id, @Param("tenantId") Long tenantId);

    Appointment findById(@Param("id") Long id, @Param("tenantId") Long tenantId);

    int countByPatient(@Param("patientId") Long patientId,
                       @Param("tenantId") Long tenantId,
                       @Param("status") String status,
                       @Param("beginDate") LocalDate beginDate,
                       @Param("endDate") LocalDate endDate);

    List<Appointment> pageByPatient(@Param("patientId") Long patientId,
                                    @Param("tenantId") Long tenantId,
                                    @Param("status") String status,
                                    @Param("beginDate") LocalDate beginDate,
                                    @Param("endDate") LocalDate endDate,
                                    @Param("offset") int offset,
                                    @Param("limit") int limit);

    int updateStatus(@Param("id") Long id, @Param("status") String status);

    int updateSchedule(@Param("id") Long id,
                       @Param("regDate") LocalDate regDate,
                       @Param("timeRange") String timeRange);

    /** 某医生某天某时段已占用的号源数（不含已取消） */
    int countSlot(@Param("doctorId") Long doctorId,
                  @Param("regDate") LocalDate regDate,
                  @Param("timeRange") String timeRange);

    /** 报表：按日期 + 状态汇总，sort/order 由 service 白名单校验后传入 */
    List<Map<String, Object>> reportRows(@Param("tenantId") Long tenantId,
                                         @Param("sort") String sort,
                                         @Param("order") String order);
}
