package com.example;

import javax.servlet.http.HttpServletResponse;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/redirect")
public class RedirectController {
    @GetMapping("/go")
    public void go(@RequestParam String target, HttpServletResponse response) throws Exception {
        if (!target.startsWith("/")) {
            throw new RuntimeException("invalid redirect");
        }
        response.sendRedirect(target);
    }
}
