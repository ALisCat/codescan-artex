package com.community.clinic.mapper;

import com.community.clinic.model.SysUser;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface SysUserMapper {

    @Select("select id, name, phone, password, role, tenant_id from sys_user where phone = #{phone} limit 1")
    SysUser findByPhone(@Param("phone") String phone);
}
