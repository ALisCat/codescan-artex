#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQL 注入分析器：只找「SQL 构造」是否出现在接口 flow 里。

不区分 #{}/?/${}/wrapper 是否安全——只把它们作为 evidence/guards_seen。
"""
import re
from pathlib import Path

import yaml

from .base import Analyzer, Finding, POSSIBLE, IMPOSSIBLE, UNKNOWN

CATALOG = Path(__file__).resolve().parents[1] / "catalogs" / "sql_injection.yaml"


class SqlInjectionAnalyzer(Analyzer):
    vulnclass = "sql-injection"

    def __init__(self):
        self.c = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
        self.jdbc_pats = [re.compile(p) for p in self.c.get("jdbc", [])]
        self.raw_wrapper = set(self.c.get("wrapper_raw", []))
        self.param_wrapper = set(self.c.get("wrapper_parameterized", []))
        self.dollar_re = re.compile(self.c.get("sql_dollar", r"\$\{"))
        self.placeholder_re = re.compile(self.c.get("sql_placeholder", r"#\{|\?"))
        self.guard_pats = [re.compile(p) for p in self.c.get("guards", [])]
        self.unresolved_re = re.compile(self.c.get("unresolved_relevant", r"(?i)service$"))

    def analyze(self, endpoint, ctx):
        sites = []
        seen = set()
        class_fqns = {c.get("fqn") for c in ctx.graph.get("classes", [])}

        # 1) 图里已识别的 DAO / mapper / wrapper
        for d in endpoint.get("daos", []):
            site = d.get("sql_site") or {}
            sql = (site.get("sql") or "")
            wrappers = d.get("wrapper", [])
            raw_signals = []
            param_signals = []
            for w in wrappers:
                if w.get("name") in self.raw_wrapper:
                    raw_signals.append(w["name"])
                elif w.get("name") in self.param_wrapper:
                    param_signals.append(w["name"])
            if self.dollar_re.search(sql):
                raw_signals.append("${}")
            if self.placeholder_re.search(sql):
                param_signals.append("#{}")

            key = ("dao", d.get("call_file"), d.get("call_line"), d.get("method"))
            if key in seen:
                continue
            seen.add(key)
            sites.append({
                "kind": d.get("sql_kind") or "unknown",
                "dao": d.get("dao"),
                "method": d.get("method"),
                "file": d.get("call_file"),
                "line": d.get("call_line"),
                "sql": sql[:800],
                "sql_file": site.get("file"),
                "sql_line": site.get("line"),
                "raw_signals": sorted(set(raw_signals)),
                "parameterized_signals": sorted(set(param_signals)),
                "wrapper": [
                    {"name": w.get("name"), "file": w.get("file"), "line": w.get("line")}
                    for w in wrappers[:8]
                ],
            })

        # 2) flow 里直接出现的 JDBC 调用
        for step in endpoint.get("flow", []):
            if step.get("kind") != "method":
                continue
            for pat in self.jdbc_pats:
                for file, line, text in ctx.find(step, pat):
                    key = ("jdbc", file, line, text[:40])
                    if key in seen:
                        continue
                    seen.add(key)
                    snippet = ctx.read(file, max(1, line - 1), line + 5)
                    sites.append({
                        "kind": "jdbc",
                        "api": text[:80],
                        "file": file,
                        "line": line,
                        "sql": snippet[:800],
                        "raw_signals": [],
                        "parameterized_signals": [],
                    })

        # 3) 输入前提：没有请求参数就不可能是注入
        has_input = bool(endpoint.get("params"))

        # 4) 未知：图里未解析、但可能是 service/dao 的调用
        ACCESSOR = re.compile(r"^(get|set|is)[A-Z]")
        IGNORE = {"parseObj", "parseObject", "toJson", "writeValueAsString", "readTree",
                  "info", "error", "debug", "warn", "equals", "toString", "put", "getStr",
                  "decodeStr", "isNotEmpty", "isBlank", "noneMatch", "stream", "fromJson",
                  "getType", "getKey", "getValue", "size", "add", "collect"}

        def relevant(u):
            name = u.get("name") or ""
            if ACCESSOR.match(name) or name in IGNORE:
                return False
            if self.unresolved_re.search(name):
                return True
            sc = (u.get("scope") or "").split("<")[0].strip()
            if sc in class_fqns:
                return True
            caller = (u.get("caller_cls") or "").split(".")[-1]
            if re.search(r"(?i)(Service|Client|Manager|Repository|Mapper|Dao)$", caller):
                return True
            text = u.get("scopeText") or ""
            return bool(re.search(r"(?i)(Service|Client|Manager|Repository|Mapper|Dao)$", text))

        relevant_unresolved = [u for u in endpoint.get("unresolved", []) if relevant(u)]

        guards_seen = []
        gseen = set()
        for s in sites:
            for sig in s.get("parameterized_signals", []):
                key = ("parameterized", s.get("file"), s.get("line"), sig)
                if key in gseen:
                    continue
                gseen.add(key)
                guards_seen.append({"kind": "parameterized", "text": sig,
                                    "file": s.get("sql_file") or s.get("file"),
                                    "line": s.get("sql_line") or s.get("line")})
        for step in endpoint.get("flow", []):
            if step.get("kind") != "method":
                continue
            for pat in self.guard_pats:
                for file, line, text in ctx.find(step, pat):
                    key = ("guard", file, line)
                    if key in gseen:
                        continue
                    gseen.add(key)
                    guards_seen.append({"kind": "guard", "text": text[:80], "file": file, "line": line})

        if not has_input:
            state = IMPOSSIBLE
            missing = "no request input"
        elif sites:
            state = POSSIBLE
            missing = None
        elif relevant_unresolved:
            state = UNKNOWN
            missing = "unresolved: " + "; ".join(
                "%s:%s %s" % (u.get("file"), u.get("line"), u.get("name"))
                for u in relevant_unresolved[:3]
            )
        else:
            state = IMPOSSIBLE
            missing = None

        evidence = {
            "sql_sites": sites[:10],
            "params": endpoint.get("params", []),
            "has_input": has_input,
        }
        return [Finding.make(endpoint, self.vulnclass, state, evidence, guards_seen, missing)]
