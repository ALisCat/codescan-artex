package com.example;

import java.net.URL;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/fetch")
public class SsrfController {
    @GetMapping("/health")
    public String health() throws Exception {
        return new URL("http://example.com").openConnection().toString();
    }
}
