package com.example;

import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/ldap")
public class LdapController {
    @PostMapping("/search")
    public String search(@RequestParam String uid) throws Exception {
        DirContext ctx = new InitialDirContext();
        String filter = "(uid=" + uid + ")";
        ctx.search("dc=example", filter, null);
        return "ok";
    }
}
