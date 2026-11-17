package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/command")
public class CommandController {
    @GetMapping("/status")
    public String status() throws Exception {
        Runtime.getRuntime().exec("uptime");
        return "ok";
    }
}
