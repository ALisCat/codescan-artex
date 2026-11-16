#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析器共享的未解析调用判定。"""
import re

ACCESSOR = re.compile(r"^(get|set|is)[A-Z]")
IGNORE = {"parseObj", "parseObject", "toJson", "writeValueAsString", "readTree",
          "info", "error", "debug", "warn", "equals", "toString", "put", "getStr",
          "decodeStr", "isNotEmpty", "isBlank", "noneMatch", "stream", "fromJson",
          "getType", "getKey", "getValue", "size", "add", "collect"}


def relevant_unresolved(endpoint, ctx, name_re):
    class_fqns = {c.get("fqn") for c in ctx.graph.get("classes", [])}
    out = []
    for u in endpoint.get("unresolved", []):
        name = u.get("name") or ""
        if ACCESSOR.match(name) or name in IGNORE:
            continue
        if name_re and name_re.search(name):
            out.append(u); continue
        sc = (u.get("scope") or "").split("<")[0].strip()
        if sc in class_fqns:
            out.append(u); continue
        caller = (u.get("caller_cls") or "").split(".")[-1]
        if re.search(r"(?i)(Service|Client|Manager|Repository|Mapper|Dao)$", caller):
            out.append(u); continue
        text = u.get("scopeText") or ""
        if re.search(r"(?i)(Service|Client|Manager|Repository|Mapper|Dao)$", text):
            out.append(u)
    return out
