package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/user")
public class UserController {
    private final UserMapper mapper = null;

    @GetMapping("/{id}")
    public String get(@PathVariable Long id) {
        return mapper.selectById(id);
    }
}
