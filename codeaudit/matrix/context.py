#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析上下文：图 + 按 file:line 读源码。"""
import re
from collections import defaultdict
from pathlib import Path


class AnalysisContext:
    def __init__(self, graph, root=None):
        self.graph = graph
        self.root = Path(root or graph.get("root") or ".")
        self.methods = {m["id"]: m for m in graph.get("methods", [])}
        self.calls_by = defaultdict(list)
        for c in graph.get("calls", []):
            self.calls_by[c["caller"]].append(c)
        self.xml_sites = {(s["dao"], s["method"]): s for s in graph.get("xml_sites", [])}
        self._cache = {}

    def read(self, file, start, end):
        lines = self._cache.get(file)
        if lines is None:
            p = self.root / file
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                lines = []
            self._cache[file] = lines
        s = max(0, int(start or 1) - 1)
        e = min(len(lines), int(end or start or 1))
        return "\n".join(lines[s:e])

    def method_body(self, step):
        if step.get("kind") != "method":
            return ""
        return self.read(step["file"], step.get("line"), step.get("end"))

    def find(self, step, pattern):
        """在方法体里找 pattern，返回 (file, line, text)。"""
        body = self.method_body(step)
        if not body:
            return
        for m in re.finditer(pattern, body):
            line = (step.get("line") or 1) + body[: m.start()].count("\n")
            yield step["file"], line, m.group(0)

    def calls_in(self, step):
        mid = step.get("method_id")
        return self.calls_by.get(mid, []) if mid else []

    def sql_of(self, dao, method):
        return self.xml_sites.get((dao, method))

    def endpoints(self):
        return self.graph.get("endpoints", [])
