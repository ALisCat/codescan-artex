#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Open redirect：重定向目标是否来自请求参数。"""
import re

from .base import Analyzer, Finding, POSSIBLE, IMPOSSIBLE
from .patterns import scan, has_input, model, search_policy

REDIRECT = [
    re.compile(r"(?i)(sendRedirect|setHeader\s*\(\s*[\"']Location|RedirectView|redirect\s*:)"),
]
ALLOW = [
    re.compile(r"(?i)(allowlist|allowedHost|startsWith\s*\(\s*[\"']/|equals\s*\(\s*[\"']/|isSafeRedirect|validateRedirect)"),
]


class OpenRedirectAnalyzer(Analyzer):
    vulnclass = "open_redirect"

    def analyze(self, endpoint, ctx):
        sites = scan(ctx, endpoint, REDIRECT, "redirect")
        if not sites or not has_input(endpoint):
            return [Finding.make(endpoint, self.vulnclass, IMPOSSIBLE, {
                "scope": "endpoint", "subtype": "no-user-controlled-redirect",
            }, [], "no redirect with request input")]
        guards = scan(ctx, endpoint, ALLOW, "redirect_allowlist")
        gaps = [] if guards else ["redirect_target_not_allowlisted"]
        m = model(["redirect_target_allowlisted"], sites + guards, gaps, extra={
            "redirects": sites[:10],
            "search_policy": search_policy(gaps, ["allowlist|allowedHost|startsWith|isSafeRedirect"]),
        })
        ev = {
            "open_redirect_model": m, "scope": "endpoint",
            "subtype": "open-redirect" if gaps else "redirect-allowlisted",
            "cwe": ["CWE-601"], "tags": ["open-redirect"],
            "sites": sites[:10],
        }
        return [Finding.make(endpoint, self.vulnclass, POSSIBLE, ev, [], gaps[0] if gaps else None)]
