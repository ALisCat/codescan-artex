package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/ldap")
public class LdapController {
    @PostMapping("/echo")
    public String echo(@RequestBody String body) { return body; }
}
