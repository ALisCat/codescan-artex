package com.community.clinic.mapper;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface SysConfigMapper {

    @Select("select cfg_value from sys_config where tenant_id = #{tenantId} and cfg_key = #{key}")
    String findValue(@Param("tenantId") Long tenantId, @Param("key") String key);

    @Insert("insert into sys_config (tenant_id, cfg_key, cfg_value) values (#{tenantId}, #{key}, #{value}) "
            + "on conflict (tenant_id, cfg_key) do update set cfg_value = excluded.cfg_value")
    int upsert(@Param("tenantId") Long tenantId, @Param("key") String key, @Param("value") String value);
}
