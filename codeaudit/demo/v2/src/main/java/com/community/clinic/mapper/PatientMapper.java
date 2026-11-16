package com.community.clinic.mapper;

import com.community.clinic.model.Patient;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface PatientMapper {

    @Select("select id, name, phone, password, id_card, tenant_id from patient where phone = #{phone} limit 1")
    Patient findByPhone(@Param("phone") String phone);

    @Select("select id, name, phone, password, id_card, tenant_id from patient where id = #{id}")
    Patient findById(@Param("id") Long id);
}
