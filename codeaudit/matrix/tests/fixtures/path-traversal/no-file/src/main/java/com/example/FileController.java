package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/file")
public class FileController {
    @GetMapping("/info")
    public String info(@RequestParam String path) { return path; }
}
