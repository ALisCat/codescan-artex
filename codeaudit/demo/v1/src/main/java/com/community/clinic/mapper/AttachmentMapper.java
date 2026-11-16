package com.community.clinic.mapper;

import com.community.clinic.model.Attachment;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface AttachmentMapper {

    @Insert("insert into attachment (patient_id, file_name, file_path, upload_time) "
            + "values (#{patientId}, #{fileName}, #{filePath}, #{uploadTime})")
    @Options(useGeneratedKeys = true, keyProperty = "id", keyColumn = "id")
    int insert(Attachment attachment);

    @Select("select id, patient_id, file_name, file_path, upload_time from attachment "
            + "where file_path = #{filePath} limit 1")
    Attachment findByFilePath(@Param("filePath") String filePath);
}
