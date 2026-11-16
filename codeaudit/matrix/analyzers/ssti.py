#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SSTI：模板/表达式引擎是否使用请求数据。"""
import re

from .base import Analyzer, Finding, POSSIBLE, IMPOSSIBLE
from .patterns import scan, has_input, model, search_policy

ENGINE = [
    re.compile(r"(?i)(SpelExpressionParser|ExpressionParser|Ognl|TemplateEngine|Freemarker|Velocity|Thymeleaf|SpringTemplateEngine|process\s*\()"),
]
GUARD = [
    re.compile(r"(?i)(Sandbox|sandbox|SecureTemplate|allowedExpression|SimpleEvaluationContext|whitelist)"),
]


class SstiAnalyzer(Analyzer):
    vulnclass = "ssti"

    def analyze(self, endpoint, ctx):
        sites = scan(ctx, endpoint, ENGINE, "template_engine")
        if not sites or not has_input(endpoint):
            return [Finding.make(endpoint, self.vulnclass, IMPOSSIBLE, {
                "scope": "endpoint", "subtype": "no-template-expression",
            }, [], "no template/expression engine with request input")]
        guards = scan(ctx, endpoint, GUARD, "template_sandbox")
        gaps = [] if guards else ["template_expression_not_sandboxed"]
        m = model(["template_expression_sandboxed"], sites + guards, gaps, extra={
            "engines": sites[:10],
            "search_policy": search_policy(gaps, ["Sandbox|SimpleEvaluationContext|allowedExpression"]),
        })
        ev = {
            "ssti_model": m, "scope": "endpoint",
            "subtype": "ssti" if gaps else "template-sandboxed",
            "cwe": ["CWE-94"], "tags": ["ssti"],
            "sites": sites[:10],
        }
        return [Finding.make(endpoint, self.vulnclass, POSSIBLE, ev, [], gaps[0] if gaps else None)]
