#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""authz 分析器：只找「资源访问 + 资源参数 + principal/归属证据」。

不判断归属是否有效、也不判断是否可绕过——这些交给 worker。
"""
import re
from pathlib import Path

import yaml

from .base import Analyzer, Finding, POSSIBLE, IMPOSSIBLE, UNKNOWN
from ..guards.engine import build_authz_model

CATALOG = Path(__file__).resolve().parents[1] / "catalogs" / "authz.yaml"


class AuthzAnalyzer(Analyzer):
    vulnclass = "authz"

    def __init__(self):
        self.c = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
        self.db_pats = [re.compile(p) for p in self.c.get("resource_db", [])]
        self.file_pats = [re.compile(p) for p in self.c.get("resource_file", [])]
        self.ext_pats = [re.compile(p) for p in self.c.get("resource_external", [])]
        self.principal_pats = [re.compile(p) for p in self.c.get("principal", [])]
        self.owner_pats = [re.compile(p) for p in self.c.get("ownership", [])]
        self.tenant_re = re.compile(self.c.get("tenant_param", r"(?i)tenant"))
        self.unresolved_re = re.compile(self.c.get("unresolved_relevant", r"(?i)service$"))

    def _scan(self, ctx, step, patterns, kind, out, seen):
        for pat in patterns:
            for file, line, text in ctx.find(step, pat):
                key = (kind, file, line)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"kind": kind, "file": file, "line": line, "api": text[:80]})

    def analyze(self, endpoint, ctx):
        class_fqns = {c.get("fqn") for c in ctx.graph.get("classes", [])}
        resources = []
        seen = set()

        # DB：图里已经解析出的 DAO 调用
        for d in endpoint.get("daos", []):
            key = ("db", d.get("call_file"), d.get("call_line"))
            if key in seen:
                continue
            seen.add(key)
            resources.append({
                "kind": "db",
                "dao": d.get("dao"),
                "method": d.get("method"),
                "sql_kind": d.get("sql_kind"),
                "file": d.get("call_file"),
                "line": d.get("call_line"),
            })

        # 文件 / 外部调用：沿 flow 读源码
        for step in endpoint.get("flow", []):
            if step.get("kind") != "method":
                continue
            self._scan(ctx, step, self.db_pats, "db", resources, seen)
            self._scan(ctx, step, self.file_pats, "file", resources, seen)
            self._scan(ctx, step, self.ext_pats, "external", resources, seen)

        # principal / 归属证据（只记录，不改变 state）
        guards = []
        gseen = set()
        for step in endpoint.get("flow", []):
            if step.get("kind") != "method":
                continue
            self._scan(ctx, step, self.principal_pats, "principal", guards, gseen)
            self._scan(ctx, step, self.owner_pats, "ownership", guards, gseen)

        # tenant 来源：token / 请求参数
        tenant_params = [p.get("name") for p in endpoint.get("params", [])
                         if self.tenant_re.search(p.get("name") or "")]
        has_principal = any(g["kind"] == "principal" for g in guards)
        tenant_source = "principal" if has_principal else ("request" if tenant_params else "none")

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
            if re.search(r"(?i)(Service|Client|Manager|Repository|Notice|Push|His)$", caller):
                return True
            text = u.get("scopeText") or ""
            if re.search(r"(?i)(Service|Client|Manager|Repository|Mapper|Dao)$", text):
                return True
            return False

        relevant_unresolved = [u for u in endpoint.get("unresolved", []) if relevant(u)]
        missing = None
        public = re.search(r"(?i)/(auth/(login|register)|login|health|error)(/|$)", endpoint.get("url") or "")
        if public:
            state = IMPOSSIBLE
            missing = "公开接口/认证入口，不做资源授权"
        elif resources:
            state = POSSIBLE
        elif relevant_unresolved:
            state = UNKNOWN
            missing = "unresolved: " + "; ".join(
                "%s:%s %s" % (u.get("file"), u.get("line"), u.get("name"))
                for u in relevant_unresolved[:3]
            )
        else:
            state = IMPOSSIBLE

        authz_model, guard_helpers = build_authz_model(endpoint, ctx, resources, guards)
        evidence = {
            "resource_accesses": resources[:20],
            "params": endpoint.get("params", []),
            "tenant_source": tenant_source,
            "tenant_params": tenant_params,
            "authz_model": authz_model,
            "guard_helpers": guard_helpers,
        }
        return [Finding.make(endpoint, self.vulnclass, state, evidence, guards, missing)]
