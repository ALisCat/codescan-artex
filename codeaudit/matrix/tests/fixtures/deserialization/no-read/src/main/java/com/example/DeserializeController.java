package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/deserialize")
public class DeserializeController {
    @PostMapping("/echo")
    public String echo(@RequestBody String body) { return body; }
}
