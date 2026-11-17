package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/pay")
public class PayController {
    @PostMapping("/notify")
    public String notify(@RequestBody String body,
                         @RequestHeader("sign") String sign,
                         @RequestHeader("timestamp") String timestamp) {
        verifySign(sign, body);
        checkTimestamp(timestamp);
        return "ok";
    }

    private void verifySign(String sign, String body) {
        if (sign == null) {
            throw new RuntimeException("bad sign");
        }
    }

    private void checkTimestamp(String timestamp) {
        if (timestamp == null) {
            throw new RuntimeException("expired");
        }
    }
}
