package com.example;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/admin/orders")
public class AdminOrderController {
    private final OrderService service = new OrderService();

    @PreAuthorize("hasRole('ADMIN')")
    @GetMapping("/{id}")
    public String detail(@PathVariable Long id) {
        return service.detail(id).getData();
    }
}
