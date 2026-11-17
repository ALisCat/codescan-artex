package com.example;

import java.io.File;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/file")
public class FileController {
    @GetMapping("/config")
    public String config() {
        return new File("/etc/hosts").toString();
    }
}
