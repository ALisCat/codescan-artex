package com.example;

public class OrderService {
    private final OrderMapper mapper = new OrderMapper();

    public String detail(Long id) {
        return mapper.selectById(id);
    }
}
