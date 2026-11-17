package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/plain")
public class PlainController {
    @PostMapping("/echo")
    public String echo(@RequestBody String body) {
        return body;
    }
}
