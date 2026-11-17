#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQL 注入特征分析器。

只识别 SQL 注入的风险特征：
  - ${} 原始插值
  - 字符串拼接 / format 构造 SQL
  - 动态表名、列名、ORDER BY、raw wrapper
  - 无法解析的 SQL/provider

不判断特征是否可达、是否有守卫、是否最终可利用。
#{ } / ? / eq 等值绑定不是 SQL 注入特征，只记 neutralizer。
"""
import re
from pathlib import Path

import yaml

from .base import Analyzer, Finding, POSSIBLE, IMPOSSIBLE, UNKNOWN
from .sql_features import collect

CATALOG = Path(__file__).resolve().parents[1] / "catalogs" / "sql_injection.yaml"


class SqlInjectionAnalyzer(Analyzer):
    vulnclass = "sql-injection"

    def __init__(self):
        self.c = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
        self.jdbc_pats = [re.compile(p) for p in self.c.get("jdbc", [])]
        self.guard_pats = [re.compile(p) for p in self.c.get("guards", [])]
        self.unresolved_re = re.compile(self.c.get("unresolved_relevant", r"(?i)service$"))

    def analyze(self, endpoint, ctx):
        sites, features, unknowns, neutralizers = collect(endpoint, ctx, self.jdbc_pats)

        guards_seen = []
        gseen = set()
        for step in endpoint.get("flow", []):
            if step.get("kind") != "method":
                continue
            for pat in self.guard_pats:
                for file, line, text in ctx.find(step, pat):
                    key = ("guard", file, line)
                    if key in gseen:
                        continue
                    gseen.add(key)
                    guards_seen.append({"kind": "guard", "text": text[:80],
                                        "file": file, "line": line})

        class_fqns = {c.get("fqn") for c in ctx.graph.get("classes", [])}
        ACCESSOR = re.compile(r"^(get|set|is)[A-Z]")
        IGNORE = {"parseObj", "parseObject", "toJson", "writeValueAsString", "readTree",
                  "info", "error", "debug", "warn", "equals", "toString", "put", "getStr",
                  "decodeStr", "isNotEmpty", "isBlank", "noneMatch", "stream", "fromJson",
                  "getType", "getKey", "getValue", "size", "add", "collect"}

        SQL_STRONG = re.compile(
            r"(?i)(sql|query|select|executeQuery|executeUpdate|executeBatch|"
            r"batch|mapper|dao|repository|selectOne|selectList|selectPage|"
            r"selectById|find|fetch|search|load)"
        )
        SQL_CRUD = re.compile(
            r"(?i)(insert|update|delete|save|remove|count|list|page|get|put)"
        )

        def relevant(u):
            name = u.get("name") or ""
            if ACCESSOR.match(name) or name in IGNORE:
                return False
            sc = (u.get("scope") or "").split("<")[0].strip()
            text = u.get("scopeText") or ""
            scope_dao = bool(re.search(r"(?i)(Mapper|Dao|Repository)$", sc + " " + text))
            # Strong SQL names are relevant even without a DAO-looking receiver.
            if SQL_STRONG.search(name):
                return True
            # Generic CRUD/list names are relevant only on a DAO-looking receiver;
            # otherwise "list"/"get"/"delete" from collections/Redis/utilities
            # would become SQL unknown noise.
            if SQL_CRUD.search(name) and scope_dao:
                return True
            if self.unresolved_re.search(name) and scope_dao:
                return True
            if scope_dao and sc in class_fqns:
                return True
            return False

        relevant_unresolved = [u for u in endpoint.get("unresolved", []) if relevant(u)]

        # State = feature association, not a security verdict.
        if features:
            state = POSSIBLE
            missing = None
        elif unknowns:
            state = UNKNOWN
            missing = "; ".join(u.get("reason") or "unknown SQL feature" for u in unknowns[:3])
        elif relevant_unresolved:
            state = UNKNOWN
            missing = "unresolved: " + "; ".join(
                "%s:%s %s" % (u.get("file"), u.get("line"), u.get("name"))
                for u in relevant_unresolved[:3]
            )
        else:
            state = IMPOSSIBLE
            missing = None

        dedup_neutralizers = []
        nseen = set()
        for n in neutralizers:
            key = (n.get("kind"), n.get("method"), n.get("file"), n.get("line"))
            if key in nseen:
                continue
            nseen.add(key)
            dedup_neutralizers.append(n)

        if features:
            sql_mode = "raw"
        elif unknowns or relevant_unresolved:
            sql_mode = "unknown"
        elif dedup_neutralizers:
            sql_mode = "parameterized_only"
        else:
            sql_mode = "no_sql"

        evidence = {
            "sql_sites": sites[:10],
            "sql_features": features[:20],
            "sql_mode": sql_mode,
            "neutralizers": dedup_neutralizers[:20],
            "params": endpoint.get("params", []),
            "has_input": bool(endpoint.get("params")),
        }
        return [Finding.make(endpoint, self.vulnclass, state, evidence, guards_seen, missing)]
