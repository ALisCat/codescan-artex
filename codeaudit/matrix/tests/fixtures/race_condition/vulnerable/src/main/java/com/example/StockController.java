package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/stock")
public class StockController {
    private final StockService service = new StockService();

    @PostMapping("/deduct")
    public String deduct(@RequestParam Long stockId) {
        service.decrement(stockId);
        return "ok";
    }
}
