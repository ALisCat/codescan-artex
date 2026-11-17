package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/token")
public class TokenController {
    @PostMapping("/refresh")
    public String refresh(@RequestBody String token) {
        return token;
    }
}
