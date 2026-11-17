package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/user")
public class UserController {
    private final UserMapper mapper = null;

    @GetMapping("/list")
    public String list(@RequestParam Long id, @RequestParam String sort) {
        return mapper.selectList(id, sort);
    }
}
