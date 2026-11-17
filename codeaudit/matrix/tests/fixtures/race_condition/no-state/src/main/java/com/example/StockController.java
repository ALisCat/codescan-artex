package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/stock")
public class StockController {
    @GetMapping("/list")
    public String list() { return "ok"; }
}
