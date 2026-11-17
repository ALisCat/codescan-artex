package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderService service = new OrderService();

    @GetMapping("/{id}")
    public String detail(@PathVariable Long id) {
        return service.detail(id);
    }
}
