#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓库级 crypto：弱算法/ECB/硬编码 key。"""
from ..base import Analyzer
from .common import scan_text, repo_finding

PATTERNS = [
    r"(?i)AES/ECB",
    r"(?i)(AES_KEY|SECRET_KEY|ENCRYPTION_KEY|PRIVATE_KEY)\s*=\s*[\"'][^\"']+[\"']",
    r"(?i)(MD5|SHA-?1)[^;\n]{0,80}(password|passwd|credential)",
]


class CryptoAnalyzer(Analyzer):
    vulnclass = "crypto"
    scope = "repo"

    def analyze(self, ctx):
        sites = []
        for p in PATTERNS:
            sites.extend(scan_text(ctx, p, "weak_crypto"))
        seen, uniq = set(), []
        for s in sites:
            k = (s.get("file"), s.get("line"), s.get("kind"))
            if k in seen:
                continue
            seen.add(k); uniq.append(s)
        if not uniq:
            return []
        return [repo_finding(
            self.vulnclass, "repo://crypto", "weak-or-hardcoded-crypto",
            ["CWE-327", "CWE-329"], ["crypto", "repo"],
            uniq, ["strong_crypto_and_key_management"], ["weak_crypto_or_hardcoded_key"],
            ["AES/GCM|RSA-OAEP|KMS|KeyStore"], "weak crypto / hardcoded key found",
        )]
