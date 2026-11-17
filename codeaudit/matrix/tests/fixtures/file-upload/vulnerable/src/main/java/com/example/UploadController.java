package com.example;

import java.io.File;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/upload")
public class UploadController {
    @PostMapping("/file")
    public String upload(@RequestParam MultipartFile file) throws Exception {
        file.transferTo(new File("/tmp/" + file.getOriginalFilename()));
        return "ok";
    }
}
