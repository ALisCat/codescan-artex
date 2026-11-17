package com.example;

import java.util.Map;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/auth")
public class AuthController {
    @PostMapping("/login")
    public Map<String, Object> login(@RequestBody Map<String, String> body) {
        return body;
    }
}
