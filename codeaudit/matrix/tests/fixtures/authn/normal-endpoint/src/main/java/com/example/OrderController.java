package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    @GetMapping("/{id}")
    public String detail(@PathVariable Long id) {
        return "ok";
    }
}
