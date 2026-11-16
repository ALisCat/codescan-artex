package com.example.clinic.mapper;

import com.example.clinic.model.ClinicModels.Attachment;
import com.example.clinic.model.ClinicModels.LoginUser;
import com.example.clinic.model.ClinicModels.Patient;
import com.example.clinic.model.ClinicModels.SysConfig;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface ClinicMapper {

    LoginUser findLoginUser(@Param("username") String username);

    Patient findPatientById(@Param("id") Long id);

    List<Attachment> findAttachmentsByAppointmentId(@Param("appointmentId") Long appointmentId);

    Attachment findAttachmentById(@Param("id") Long id);

    int insertAttachment(Attachment attachment);

    int insertNotice(@Param("patientId") Long patientId,
                     @Param("channel") String channel,
                     @Param("title") String title,
                     @Param("content") String content,
                     @Param("createdBy") Long createdBy);

    SysConfig findConfig(@Param("configKey") String configKey);

    int upsertConfig(SysConfig config);
}
