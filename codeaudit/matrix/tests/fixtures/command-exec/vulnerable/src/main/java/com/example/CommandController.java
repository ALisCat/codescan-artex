package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/command")
public class CommandController {
    @GetMapping("/run")
    public String run(@RequestParam String cmd) throws Exception {
        Runtime.getRuntime().exec(cmd);
        return "ok";
    }
}
