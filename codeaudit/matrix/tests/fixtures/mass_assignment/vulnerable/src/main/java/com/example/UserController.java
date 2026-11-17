package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/user")
public class UserController {
    private final UserService service = new UserService();

    @PostMapping("/update")
    public String update(@RequestBody UserDTO dto) {
        class Payload {
            private String role;
            private String tenantId;
        }
        service.save(dto);
        return "ok";
    }
}
