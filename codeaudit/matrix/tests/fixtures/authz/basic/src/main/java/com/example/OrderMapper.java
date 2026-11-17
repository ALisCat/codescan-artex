package com.example;

public class OrderMapper {
    public String selectById(Long id) {
        return "select * from orders where id=" + id;
    }
}
