package com.example;

import java.io.File;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/file")
public class FileController {
    @GetMapping("/read")
    public String read(@RequestParam String path) throws Exception {
        return new File(path).toString();
    }
}
