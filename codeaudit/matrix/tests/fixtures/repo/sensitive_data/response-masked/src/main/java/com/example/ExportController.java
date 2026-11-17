package com.example;

import javax.servlet.http.HttpServletResponse;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/export")
public class ExportController {
    @GetMapping("/user")
    public void user(String phone, HttpServletResponse response) throws Exception {
        response.getWriter().write(mask(phone));
    }
    private String mask(String phone) { return "***"; }
}
