package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/notify")
public class NotifyController {
    @GetMapping("/callback")
    public String callback() {
        return "ok";
    }
}
