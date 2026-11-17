package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/order")
public class OrderController {
    @GetMapping("/list")
    public String list() { return "ok"; }
}
