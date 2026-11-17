package com.example;

import java.net.URL;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/fetch")
public class SsrfController {
    @GetMapping("/url")
    public String fetch(@RequestParam String url) throws Exception {
        return new URL(url).openConnection().toString();
    }
}
