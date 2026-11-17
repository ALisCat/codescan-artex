package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/redirect")
public class RedirectController {
    @GetMapping("/info")
    public String info() { return "ok"; }
}
