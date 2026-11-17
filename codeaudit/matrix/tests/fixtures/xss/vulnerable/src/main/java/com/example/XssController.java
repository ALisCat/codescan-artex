package com.example;

import javax.servlet.http.HttpServletResponse;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/xss")
public class XssController {
    @GetMapping("/echo")
    public void echo(@RequestParam String name, HttpServletResponse response) throws Exception {
        response.getWriter().write(name);
    }
}
