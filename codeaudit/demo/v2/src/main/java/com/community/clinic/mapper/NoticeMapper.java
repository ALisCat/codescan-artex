package com.community.clinic.mapper;

import com.community.clinic.model.Notice;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;

@Mapper
public interface NoticeMapper {

    @Insert("insert into notice (title, content, channel, created_by) "
            + "values (#{title}, #{content}, #{channel}, #{createdBy})")
    @Options(useGeneratedKeys = true, keyProperty = "id", keyColumn = "id")
    int insert(Notice notice);
}
