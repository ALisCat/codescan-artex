package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/sql")
public class SqlController {
    @GetMapping("/info")
    public String info(@RequestParam String id) { return id; }
}
