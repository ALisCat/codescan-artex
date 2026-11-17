package com.example;

import java.sql.Statement;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/jdbc")
public class UserController {
    private Statement statement;

    @GetMapping("/query")
    public String query(@RequestParam String id) throws Exception {
        return statement.executeQuery("select name from users where id = " + id).toString();
    }
}
