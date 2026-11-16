#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用 sink 分析器：catalog 给 sink/guard/input，逻辑只做结构可达。"""
import re
from pathlib import Path

import yaml

from .base import Analyzer, Finding, POSSIBLE, IMPOSSIBLE, UNKNOWN
from .common import relevant_unresolved

CATALOGS = Path(__file__).resolve().parents[1] / "catalogs"


class SinkAnalyzer(Analyzer):
    vulnclass = ""
    catalog = ""
    unresolved_re = r"(?i)(service|client|manager|helper|util|mapper|dao|repository)$"

    def __init__(self):
        self.c = yaml.safe_load((CATALOGS / self.catalog).read_text(encoding="utf-8"))
        self.sink_pats = [re.compile(p) for p in self.c.get("sinks", [])]
        self.guard_pats = [re.compile(p) for p in self.c.get("guards", [])]
        self.input_cfg = self.c.get("input", {}) or {}
        self.param_re = re.compile(self.input_cfg["param_re"]) if self.input_cfg.get("param_re") else None
        self.locations = set(self.input_cfg.get("locations", []) or [])
        self.ure = re.compile(self.unresolved_re)

    def _has_input(self, endpoint):
        params = endpoint.get("params", [])
        if not params:
            return False
        if self.input_cfg.get("any"):
            return True
        for p in params:
            if p.get("location") in self.locations:
                return True
            if self.param_re and self.param_re.search(p.get("name") or ""):
                return True
        return False

    def analyze(self, endpoint, ctx):
        sites = []
        seen = set()
        for step in endpoint.get("flow", []):
            if step.get("kind") != "method":
                continue
            for pat in self.sink_pats:
                for file, line, text in ctx.find(step, pat):
                    key = (file, line, text[:40])
                    if key in seen:
                        continue
                    seen.add(key)
                    snippet = ctx.read(file, max(1, line - 1), line + 4)
                    sites.append({"file": file, "line": line, "api": text[:80], "snippet": snippet[:500]})

        guards = []
        gseen = set()
        for step in endpoint.get("flow", []):
            if step.get("kind") != "method":
                continue
            for pat in self.guard_pats:
                for file, line, text in ctx.find(step, pat):
                    key = (file, line)
                    if key in gseen:
                        continue
                    gseen.add(key)
                    guards.append({"kind": "guard", "file": file, "line": line, "text": text[:80]})

        has_input = self._has_input(endpoint)
        missing = None
        if not has_input:
            state = IMPOSSIBLE
            missing = "no request input"
        elif sites:
            state = POSSIBLE
        else:
            rel = relevant_unresolved(endpoint, ctx, self.ure)
            if rel:
                state = UNKNOWN
                missing = "unresolved: " + "; ".join(
                    "%s:%s %s" % (u.get("file"), u.get("line"), u.get("name")) for u in rel[:3]
                )
            else:
                state = IMPOSSIBLE

        evidence = {"sites": sites[:10], "params": endpoint.get("params", []), "has_input": has_input}
        return [Finding.make(endpoint, self.vulnclass, state, evidence, guards, missing)]
