#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跑分析器：graph.json → findings.json"""
import argparse
import json

from .context import AnalysisContext
from .analyzers.authz import AuthzAnalyzer
from .analyzers.authn import AuthnAnalyzer
from .analyzers.sql_injection import SqlInjectionAnalyzer
from .analyzers.command_exec import CommandExecAnalyzer
from .analyzers.ssrf import SsrfAnalyzer
from .analyzers.file_upload import FileUploadAnalyzer
from .analyzers.path_traversal import PathTraversalAnalyzer
from .analyzers.deserialization import DeserializationAnalyzer
from .analyzers.xss import XssAnalyzer

ANALYZERS = {
    "authz": AuthzAnalyzer,
    "authn": AuthnAnalyzer,
    "sql-injection": SqlInjectionAnalyzer,
    "command-exec": CommandExecAnalyzer,
    "ssrf": SsrfAnalyzer,
    "file-upload": FileUploadAnalyzer,
    "path-traversal": PathTraversalAnalyzer,
    "deserialization": DeserializationAnalyzer,
    "xss": XssAnalyzer,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("graph")
    ap.add_argument("--out", default=None)
    ap.add_argument("--analyzers", default="authz")
    args = ap.parse_args()

    graph = json.load(open(args.graph, encoding="utf-8"))
    ctx = AnalysisContext(graph)

    findings = []
    for name in [x.strip() for x in args.analyzers.split(",") if x.strip()]:
        cls = ANALYZERS.get(name)
        if not cls:
            raise SystemExit("unknown analyzer: " + name)
        a = cls()
        for ep in ctx.endpoints():
            findings.extend(a.analyze(ep, ctx))

    summary = {}
    for f in findings:
        key = f["vulnclass"] + "." + f["state"]
        summary[key] = summary.get(key, 0) + 1

    out = {"graph": args.graph, "summary": summary, "findings": findings}
    if args.out:
        open(args.out, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
