package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/order")
public class OrderController {
    private final OrderService service = new OrderService();

    @PostMapping("/pay")
    public String pay(@RequestParam Long amount,
                      @RequestParam String status,
                      @RequestParam Long orderId) {
        service.pay();
        return "ok";
    }
}
