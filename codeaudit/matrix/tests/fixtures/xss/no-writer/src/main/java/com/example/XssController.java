package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/xss")
public class XssController {
    @GetMapping("/info")
    public String info(@RequestParam String name) { return name; }
}
