package com.example;

import java.io.FileOutputStream;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/upload")
public class UploadController {
    @PostMapping("/text")
    public String upload(@RequestParam String name) throws Exception {
        new FileOutputStream("/tmp/" + name).write("x".getBytes());
        return "ok";
    }
}
