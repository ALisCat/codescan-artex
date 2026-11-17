package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderService service = new OrderService();
    private final AccessService access = new AccessService();

    @GetMapping("/{id}")
    public String detail(@PathVariable Long id) {
        LoginUser user = UserContext.require();
        Order order = service.detail(id);
        if (!access.ensureAccess(order, user)) {
            throw new BizException("forbidden");
        }
        return order.getData();
    }
}
