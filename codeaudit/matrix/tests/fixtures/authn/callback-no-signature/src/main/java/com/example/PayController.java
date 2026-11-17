package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/pay")
public class PayController {
    @PostMapping("/notify")
    public String notify(@RequestBody String body) {
        return "ok";
    }
}
