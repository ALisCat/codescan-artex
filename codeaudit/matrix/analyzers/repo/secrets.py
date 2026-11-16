#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓库级 secrets：硬编码密钥/口令/私钥。不输出密钥明文。"""
import re

from ..base import Analyzer
from .common import scan_text, repo_finding

PATTERNS = [
    r"(?i)(TOKEN_SECRET|AES_KEY|SECRET_KEY|APP_SECRET|SECRET|PASSWORD|PASSWD)\s*[:=]\s*[\"'][^$\s][^\"']{4,}",
    r"(?i)(secretKey|appSecret|api[_-]?key|access[_-]?key|client[_-]?secret)\s*[:=]\s*[\"'][^$\s][^\"']{4,}",
    r"-----BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY-----",
    r"(?i)(password|passwd)\s*:\s*[\"'][^$\s][^\"']{4,}",
]


class SecretsAnalyzer(Analyzer):
    vulnclass = "secrets"
    scope = "repo"

    def analyze(self, ctx):
        sites = []
        for p in PATTERNS:
            sites.extend(scan_text(ctx, p, "hardcoded_secret"))
        # 同文件同一行去重
        seen, uniq = set(), []
        for s in sites:
            k = (s.get("file"), s.get("line"), s.get("kind"))
            if k in seen:
                continue
            seen.add(k); uniq.append(s)
        if not uniq:
            return []
        return [repo_finding(
            self.vulnclass, "repo://secrets", "hardcoded-credentials",
            ["CWE-798", "CWE-259"], ["secrets", "repo"],
            uniq, ["secrets_outside_source"], ["hardcoded_secret"],
            ["环境变量|Vault|KMS|secret manager"], "hardcoded credentials/keys found",
        )]
