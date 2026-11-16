package com.community.clinic.service;

import com.community.clinic.common.LoginUser;
import com.community.clinic.common.UserContext;
import com.community.clinic.mapper.AppointmentMapper;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

@Service
public class ReportService {

    private final AppointmentMapper appointmentMapper;

    public ReportService(AppointmentMapper appointmentMapper) {
        this.appointmentMapper = appointmentMapper;
    }

    /**
     * 预约统计报表（CSV 文本），管理员使用。
     * sort 只允许 reg_date / status / cnt / total_fee，避免拼接任意 SQL。
     */
    public String buildCsv(String sort, String order) {
        LoginUser user = UserContext.require();
        String sortColumn = sort;
        String orderDirection = order;

        List<Map<String, Object>> rows =
                appointmentMapper.reportRows(user.getTenantId(), sortColumn, orderDirection);

        StringBuilder csv = new StringBuilder();
        csv.append("日期,状态,预约数,金额合计\n");
        for (Map<String, Object> row : rows) {
            csv.append(csvCell(row.get("reg_date"))).append(',')
                    .append(csvCell(row.get("status"))).append(',')
                    .append(csvCell(row.get("cnt"))).append(',')
                    .append(csvCell(row.get("total_fee"))).append('\n');
        }
        return csv.toString();
    }

    private String normalizeSort(String sort) {
        if ("status".equals(sort) || "cnt".equals(sort) || "total_fee".equals(sort)) {
            return sort;
        }
        return "reg_date";
    }

    private String csvCell(Object value) {
        String text = value == null ? "" : String.valueOf(value);
        if (text.contains(",") || text.contains("\"") || text.contains("\n")) {
            return "\"" + text.replace("\"", "\"\"") + "\"";
        }
        return text;
    }
}
