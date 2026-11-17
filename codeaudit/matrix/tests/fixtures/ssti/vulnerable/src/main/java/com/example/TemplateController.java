package com.example;

import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/template")
public class TemplateController {
    @PostMapping("/eval")
    public Object eval(@RequestBody String expr) {
        return new SpelExpressionParser().parseExpression(expr).getValue();
    }
}
