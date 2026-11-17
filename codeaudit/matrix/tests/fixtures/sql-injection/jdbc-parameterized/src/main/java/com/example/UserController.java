package com.example;

import java.sql.PreparedStatement;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/jdbc")
public class UserController {
    private PreparedStatement statement;

    @GetMapping("/query")
    public String query(@RequestParam String id) throws Exception {
        return statement.executeQuery("select name from users where id = ?").toString();
    }
}
