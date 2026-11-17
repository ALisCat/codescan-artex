package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final ExternalService service = new ExternalService();

    @GetMapping("/{id}")
    public String detail(@PathVariable Long id) {
        return service.load(id);
    }
}
