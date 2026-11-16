#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓库级 dependency：已知高风险依赖的粗筛（v0.1）。"""
from ..base import Analyzer
from .common import scan_text, repo_finding

PATTERNS = [
    r"(?i)fastjson.{0,80}1\.2\.(?:[0-7]\d|8[0-2])",
    r"(?i)commons-httpclient",
    r"(?i)log4j-core.{0,80}2\.(?:[0-9]|1[0-6])\.",
    r"(?i)shiro-core.{0,80}1\.[0-9]",
]


class DependencyAnalyzer(Analyzer):
    vulnclass = "dependency"
    scope = "repo"

    def analyze(self, ctx):
        sites = []
        for p in PATTERNS:
            sites.extend(scan_text(ctx, p, "known_vulnerable_dependency", skip=("node_modules/",)))
        seen, uniq = set(), []
        for s in sites:
            k = (s.get("file"), s.get("line"), s.get("kind"))
            if k in seen:
                continue
            seen.add(k); uniq.append(s)
        if not uniq:
            return []
        return [repo_finding(
            self.vulnclass, "repo://dependency", "known-vulnerable-dependency",
            ["CWE-1104"], ["dependency", "repo"],
            uniq, ["dependency_version_without_known_cve"], ["known_vulnerable_dependency"],
            ["pom.xml|gradle.lock|dependency-check|CVE database"], "known risky dependency found",
        )]
