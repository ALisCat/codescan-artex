#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CSRF：Cookie/Session 认证的状态变更接口是否校验 CSRF token。"""
import re

from .base import Analyzer, Finding, POSSIBLE, IMPOSSIBLE
from .patterns import scan, model, search_policy

SESSION = [
    re.compile(r"(?i)(HttpSession|getSession\s*\(|JSESSIONID|SecurityContext|Cookie\s*\(|@SessionAttribute)"),
]
STATE = [
    re.compile(r"(?i)@(PostMapping|PutMapping|PatchMapping|DeleteMapping)|\.(save|update|updateById|delete|remove)\s*\("),
]
CSRF = [
    re.compile(r"(?i)(csrf|xsrf|CSRFToken|X-CSRF|SameSite)"),
]


class CsrfAnalyzer(Analyzer):
    vulnclass = "csrf"

    def analyze(self, endpoint, ctx):
        if endpoint.get("method") not in ("POST", "PUT", "PATCH", "DELETE"):
            return [Finding.make(endpoint, self.vulnclass, IMPOSSIBLE, {
                "scope": "endpoint", "subtype": "not-state-changing",
            }, [], "not a state-changing method")]
        sessions = scan(ctx, endpoint, SESSION, "session_auth")
        if not sessions:
            return [Finding.make(endpoint, self.vulnclass, IMPOSSIBLE, {
                "scope": "endpoint", "subtype": "no-cookie-session",
            }, [], "no cookie/session auth evidence")]
        states = scan(ctx, endpoint, STATE, "state_change")
        if not states:
            return [Finding.make(endpoint, self.vulnclass, IMPOSSIBLE, {
                "scope": "endpoint", "subtype": "no-state-change",
            }, [], "no state change")]
        guards = scan(ctx, endpoint, CSRF, "csrf_token")
        gaps = [] if guards else ["csrf_token_missing"]
        m = model(["csrf_token"], sessions + states + guards, gaps, extra={
            "session_auth": sessions[:10],
            "state_changes": states[:10],
            "search_policy": search_policy(gaps, ["csrf|xsrf|SameSite|CSRFToken"]),
        })
        ev = {
            "csrf_model": m, "scope": "endpoint",
            "subtype": "csrf-missing" if gaps else "csrf-protected",
            "cwe": ["CWE-352"], "tags": ["csrf"],
            "sites": (sessions + states)[:10],
        }
        return [Finding.make(endpoint, self.vulnclass, POSSIBLE, ev, [], gaps[0] if gaps else None)]
