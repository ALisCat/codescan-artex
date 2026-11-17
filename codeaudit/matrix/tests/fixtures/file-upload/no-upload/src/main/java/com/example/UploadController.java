package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/upload")
public class UploadController {
    @GetMapping("/info")
    public String info() { return "ok"; }
}
