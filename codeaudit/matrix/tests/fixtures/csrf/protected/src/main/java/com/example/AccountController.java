package com.example;

import javax.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/account")
public class AccountController {
    private final AccountService service = new AccountService();

    @PostMapping("/update")
    public String update(HttpServletRequest request) {
        String csrf = request.getHeader("X-CSRF-Token");
        if (csrf == null) {
            throw new RuntimeException("missing csrf");
        }
        request.getSession().setAttribute("last", "update");
        service.save();
        return "ok";
    }
}
