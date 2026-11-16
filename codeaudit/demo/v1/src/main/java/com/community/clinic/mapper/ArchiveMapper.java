package com.community.clinic.mapper;

import com.community.clinic.model.Archive;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 档案相关 SQL 在 mapper/ArchiveMapper.xml。
 */
@Mapper
public interface ArchiveMapper {

    Archive findById(@Param("id") Long id, @Param("tenantId") Long tenantId);
}
