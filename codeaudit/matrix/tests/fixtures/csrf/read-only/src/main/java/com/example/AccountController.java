package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/account")
public class AccountController {
    @GetMapping("/profile")
    public String profile() { return "ok"; }
}
