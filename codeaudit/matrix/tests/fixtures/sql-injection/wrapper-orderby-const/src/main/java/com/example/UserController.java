package com.example;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/user")
public class UserController {
    private final UserMapper mapper = null;

    @GetMapping("/list")
    public Object list(@RequestParam String id, @RequestParam String sort) {
        LambdaQueryWrapper<User> wrapper = new LambdaQueryWrapper<>();
        wrapper.orderByAsc("name");
        return mapper.selectList(wrapper);
    }
}
