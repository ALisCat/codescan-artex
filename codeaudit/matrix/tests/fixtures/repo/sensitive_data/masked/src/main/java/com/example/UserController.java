package com.example;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
public class UserController {
    private static final Logger log = LoggerFactory.getLogger(UserController.class);
    public void show(String phone) {
        log.info("phone={}", mask(phone));
    }
    private String mask(String phone) { return "***"; }
}
