package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/fetch")
public class SsrfController {
    @GetMapping("/info")
    public String info(@RequestParam String url) { return url; }
}
