#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mass assignment：请求体是否可能直接绑定敏感字段。"""
import re

from .base import Analyzer, Finding, POSSIBLE, IMPOSSIBLE
from .patterns import scan, has_input, model, search_policy

BODY = [
    re.compile(r"@RequestBody"),
]
SENSITIVE = [
    re.compile(r"(?i)(private|public)\s+\w+\s+(role|roles|tenantId|hospId|orgId|status|enabled|admin|permission|isAdmin|password)\b"),
]
SAFE = [
    re.compile(r"(?i)(@JsonIgnore|@JsonProperty\(access\s*=\s*Access\.READ_ONLY|DTO|RequestVO|Command)"),
]
CANDIDATE = re.compile(r"(?i)(admin|user|role|profile|config|update|create|save)")


class MassAssignmentAnalyzer(Analyzer):
    vulnclass = "mass_assignment"

    def analyze(self, endpoint, ctx):
        text = "%s %s" % (endpoint.get("url") or "", endpoint.get("handler") or "")
        if endpoint.get("method") not in ("POST", "PUT", "PATCH") or not CANDIDATE.search(text) or not has_input(endpoint):
            return [Finding.make(endpoint, self.vulnclass, IMPOSSIBLE, {
                "scope": "endpoint", "subtype": "no-body-binding",
            }, [], "not a body-binding/sensitive-field candidate")]
        bodies = scan(ctx, endpoint, BODY, "request_body")
        sensitive = scan(ctx, endpoint, SENSITIVE, "sensitive_field")
        if not bodies or not sensitive:
            return [Finding.make(endpoint, self.vulnclass, IMPOSSIBLE, {
                "scope": "endpoint", "subtype": "no-sensitive-body-field",
            }, [], "no sensitive fields on request body")]
        guards = scan(ctx, endpoint, SAFE, "binding_allowlist")
        gaps = [] if guards else ["sensitive_fields_bindable"]
        m = model(["sensitive_fields_allowlisted"], bodies + sensitive + guards, gaps, extra={
            "request_body": bodies[:10],
            "sensitive_fields": sensitive[:20],
            "search_policy": search_policy(gaps, ["@JsonIgnore|READ_ONLY|DTO|RequestVO"]),
        })
        ev = {
            "mass_assignment_model": m, "scope": "endpoint",
            "subtype": "mass-assignment" if gaps else "binding-allowlisted",
            "cwe": ["CWE-915"], "tags": ["mass-assignment"],
            "sites": (bodies + sensitive)[:20],
        }
        return [Finding.make(endpoint, self.vulnclass, POSSIBLE, ev, [], gaps[0] if gaps else None)]
