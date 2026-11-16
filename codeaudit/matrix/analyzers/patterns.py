#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析器共用的小工具：沿 flow 扫源码、收集 site。"""
import re


def scan(ctx, endpoint, patterns, kind, limit=80):
    out = []
    for step in endpoint.get("flow", []):
        if step.get("kind") != "method":
            continue
        for pat in patterns:
            for file, line, text in ctx.find(step, pat):
                out.append({
                    "kind": kind, "file": file, "line": line,
                    "text": text[:160], "method": step.get("name"),
                })
                if len(out) >= limit:
                    return _dedup(out)
    return _dedup(out)


def _dedup(items):
    seen, out = set(), []
    for it in items:
        key = (it.get("kind"), it.get("file"), it.get("line"), it.get("text"))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def params(endpoint):
    return [p for p in endpoint.get("params", []) if p.get("name")]


def has_input(endpoint):
    return bool(params(endpoint)) or endpoint.get("method") in ("POST", "PUT", "PATCH", "DELETE")


def names(endpoint):
    return [str(p.get("name") or "") for p in params(endpoint)]


def model(required, decisions, gaps, unknowns=None, extra=None):
    m = {
        "required": required,
        "decisions": decisions,
        "gaps": gaps,
        "unknowns": unknowns or [],
    }
    if extra:
        m.update(extra)
    return m


def search_policy(gaps, patterns):
    return {
        "allow_global_search": bool(gaps),
        "search_budget": 2,
        "search_kinds": list(gaps),
        "search_patterns": list(dict.fromkeys(patterns)),
    }
