package com.example;

import java.util.Objects;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderService service = new OrderService();

    @GetMapping("/{id}")
    public String detail(@PathVariable Long id) {
        LoginUser user = UserContext.require();
        Order order = service.detail(id);
        if (!Objects.equals(order.getOwnerId(), user.getId())) {
            throw new BizException("forbidden");
        }
        return order.getData();
    }
}
