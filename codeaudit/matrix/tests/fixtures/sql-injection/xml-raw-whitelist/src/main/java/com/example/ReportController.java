package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/report")
public class ReportController {
    private final ReportMapper mapper = null;

    @GetMapping("/list")
    public String list(@RequestParam String sort) {
        String safeSort = normalizeSort(sort);
        return mapper.selectList(safeSort);
    }

    private String normalizeSort(String sort) {
        if (!"asc".equals(sort) && !"desc".equals(sort)) {
            return "asc";
        }
        return sort;
    }
}
