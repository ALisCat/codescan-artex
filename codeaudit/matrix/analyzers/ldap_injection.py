#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LDAP injection：LDAP filter 是否拼接请求输入。"""
import re

from .base import Analyzer, Finding, POSSIBLE, IMPOSSIBLE
from .patterns import scan, has_input, model, search_policy

LDAP = [
    re.compile(r"(?i)(InitialDirContext|DirContext|LdapTemplate|ldapTemplate|search\s*\(\s*[^,]+,\s*[^,]+,\s*[^,]+,\s*[^)]*\+)"),
]
ESCAPE = [
    re.compile(r"(?i)(LdapEncoder|escapeFilter|escapeLdap|filterEncode|LdapName|whitelist)"),
]


class LdapInjectionAnalyzer(Analyzer):
    vulnclass = "ldap_injection"

    def analyze(self, endpoint, ctx):
        sites = scan(ctx, endpoint, LDAP, "ldap_query")
        if not sites or not has_input(endpoint):
            return [Finding.make(endpoint, self.vulnclass, IMPOSSIBLE, {
                "scope": "endpoint", "subtype": "no-ldap-filter",
            }, [], "no LDAP filter with request input")]
        guards = scan(ctx, endpoint, ESCAPE, "ldap_escape")
        gaps = [] if guards else ["ldap_filter_not_escaped"]
        m = model(["ldap_filter_escaped"], sites + guards, gaps, extra={
            "ldap_calls": sites[:10],
            "search_policy": search_policy(gaps, ["LdapEncoder|escapeFilter|escapeLdap"]),
        })
        ev = {
            "ldap_model": m, "scope": "endpoint",
            "subtype": "ldap-injection" if gaps else "ldap-escaped",
            "cwe": ["CWE-90"], "tags": ["ldap"],
            "sites": sites[:10],
        }
        return [Finding.make(endpoint, self.vulnclass, POSSIBLE, ev, [], gaps[0] if gaps else None)]
