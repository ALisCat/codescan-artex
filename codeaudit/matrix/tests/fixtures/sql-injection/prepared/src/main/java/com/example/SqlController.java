package com.example;

import java.sql.PreparedStatement;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/sql")
public class SqlController {
    private PreparedStatement statement;

    @GetMapping("/query")
    public String query(@RequestParam String id) throws Exception {
        statement.setString(1, id);
        return statement.executeQuery("select * from users where id=?").toString();
    }
}
