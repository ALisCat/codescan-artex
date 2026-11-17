package com.example;

import java.sql.Statement;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/jdbc")
public class UserController {
    private Statement statement;

    @GetMapping("/query")
    public String query(@RequestParam String table) throws Exception {
        String sql = String.format("select name from %s", table);
        return statement.executeQuery(sql).toString();
    }
}
