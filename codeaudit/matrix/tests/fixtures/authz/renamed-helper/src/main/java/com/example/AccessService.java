package com.example;

import java.util.Objects;

public class AccessService {
    public boolean ensureAccess(Order order, LoginUser user) {
        return Objects.equals(order.getOwnerId(), user.getId());
    }
}
