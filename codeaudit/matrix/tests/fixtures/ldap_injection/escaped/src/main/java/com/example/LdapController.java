package com.example;

import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;
import org.springframework.ldap.support.LdapEncoder;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/ldap")
public class LdapController {
    @PostMapping("/search")
    public String search(@RequestParam String uid) throws Exception {
        DirContext ctx = new InitialDirContext();
        String filter = "(uid=" + LdapEncoder.filterEncode(uid) + ")";
        ctx.search("dc=example", filter, null);
        return "ok";
    }
}
