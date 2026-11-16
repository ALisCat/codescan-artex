package com.example.clinic.mapper;

import com.example.clinic.model.ClinicModels.Appointment;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface AppointmentMapper {

    Appointment findById(@Param("id") Long id);

    List<Appointment> findList(@Param("patientId") Long patientId,
                               @Param("status") String status,
                               @Param("doctor") String doctor);

    int cancel(@Param("id") Long id, @Param("reason") String reason);

    int reschedule(@Param("id") Long id,
                   @Param("appointmentDate") String appointmentDate,
                   @Param("doctor") String doctor);

    List<Appointment> findForReport(@Param("orderBy") String orderBy,
                                    @Param("direction") String direction);
}
