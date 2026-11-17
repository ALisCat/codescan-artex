package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/command")
public class CommandController {
    @GetMapping("/info")
    public String info(@RequestParam String cmd) { return cmd; }
}
