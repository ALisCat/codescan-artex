package com.example;
public class OrderService {
    private final OrderMapper mapper = new OrderMapper();
    public Order detail(Long id) { return mapper.selectById(id); }
}
