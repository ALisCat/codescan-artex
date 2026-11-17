package com.example;

import java.sql.Statement;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/sql")
public class SqlController {
    private Statement statement;

    @GetMapping("/query")
    public String query(@RequestParam String id) throws Exception {
        return statement.executeQuery("select * from users where id=" + id).toString();
    }
}
