#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓库级扫描工具：不绑定接口，输出 REPO finding。"""
import re

from ..base import Finding, POSSIBLE


def source_files(ctx):
    files = set()
    for m in ctx.graph.get("methods", []):
        if m.get("file"):
            files.add(m["file"])
    for c in ctx.graph.get("classes", []):
        if c.get("file"):
            files.add(c["file"])
    try:
        for pat in ("application*.yml", "application*.yaml", "application*.properties",
                    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle"):
            for p in ctx.root.rglob(pat):
                files.add(str(p.relative_to(ctx.root)))
    except Exception:
        pass
    out = []
    for f in sorted(files):
        low = f.lower()
        if any(x in low for x in ("/test/", "/tests/", ".example", "node_modules/", "/target/", "/build/")):
            continue
        out.append(f)
    return out


def scan_text(ctx, pattern, kind, limit=80, skip=()):
    rx = re.compile(pattern)
    out = []
    for f in source_files(ctx):
        if any(s in f.lower() for s in skip):
            continue
        text = ctx.read(f, 1, 20000)
        for m in rx.finditer(text):
            line = text[:m.start()].count("\n") + 1
            out.append({"kind": kind, "file": f, "line": line,
                        "text": kind, "rule": kind})
            if len(out) >= limit:
                return out
    return out


def repo_finding(vulnclass, url, subtype, cwe, tags, sites, required, gaps, patterns, missing=None):
    first = sites[0] if sites else {}
    ep = {
        "id": "REPO " + vulnclass,
        "method": "REPO",
        "url": url,
        "handler": "repo",
        "file": first.get("file"),
        "line": first.get("line") or 1,
        "params": [],
        "flow": [],
    }
    model = {
        "required": required,
        "decisions": sites[:40],
        "gaps": gaps,
        "unknowns": [],
        "search_policy": {
            "allow_global_search": bool(gaps),
            "search_budget": 2,
            "search_kinds": list(gaps),
            "search_patterns": list(dict.fromkeys(patterns)),
        },
    }
    ev = {
        "repo_model": model,
        "scope": "repo",
        "subtype": subtype,
        "cwe": cwe,
        "tags": tags,
        "sites": sites[:40],
    }
    return Finding.make(ep, vulnclass, POSSIBLE, ev, [], missing)
