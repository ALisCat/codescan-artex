#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓库级 sensitive-data：日志/响应中直接出现 PII。"""
from ..base import Analyzer
from .common import scan_text, repo_finding

PATTERNS = [
    r"(?i)log\.(?:info|debug|warn|error)\s*\([^;]{0,160}(idCard|id_card|phone|mobile|patientName|cardNo|身份证|手机号)",
    r"(?i)response\.(?:getWriter|addHeader)\s*\([^;]{0,120}(idCard|id_card|phone|mobile|patientName|cardNo|身份证|手机号)",
]


class SensitiveDataAnalyzer(Analyzer):
    vulnclass = "sensitive_data"
    scope = "repo"

    def analyze(self, ctx):
        sites = []
        for p in PATTERNS:
            sites.extend(scan_text(ctx, p, "pii_exposure"))
        seen, uniq = set(), []
        for s in sites:
            k = (s.get("file"), s.get("line"), s.get("kind"))
            if k in seen:
                continue
            seen.add(k); uniq.append(s)
        if not uniq:
            return []
        return [repo_finding(
            self.vulnclass, "repo://sensitive-data", "pii-log-or-response",
            ["CWE-532", "CWE-359"], ["sensitive-data", "repo"],
            uniq, ["pii_masked_or_removed"], ["pii_in_log_or_response"],
            ["mask|desensitize|@JsonIgnore|DTO"], "PII in log/response found",
        )]
