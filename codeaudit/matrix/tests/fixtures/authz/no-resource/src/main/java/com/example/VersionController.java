package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api")
public class VersionController {
    @GetMapping("/version")
    public String version() {
        return "1.0";
    }
}
