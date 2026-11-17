package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/template")
public class TemplateController {
    @PostMapping("/echo")
    public String echo(@RequestBody String body) { return body; }
}
