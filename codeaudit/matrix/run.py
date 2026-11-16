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
from .analyzers.business_logic import BusinessLogicAnalyzer
from .analyzers.xxe import XxeAnalyzer
from .analyzers.csrf import CsrfAnalyzer
from .analyzers.open_redirect import OpenRedirectAnalyzer
from .analyzers.ssti import SstiAnalyzer
from .analyzers.ldap_injection import LdapInjectionAnalyzer
from .analyzers.mass_assignment import MassAssignmentAnalyzer
from .analyzers.race_condition import RaceConditionAnalyzer
from .analyzers.repo.secrets import SecretsAnalyzer
from .analyzers.repo.crypto import CryptoAnalyzer
from .analyzers.repo.dependency import DependencyAnalyzer
from .analyzers.repo.sensitive_data import SensitiveDataAnalyzer

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
    "business_logic": BusinessLogicAnalyzer,
    "xxe": XxeAnalyzer,
    "csrf": CsrfAnalyzer,
    "open_redirect": OpenRedirectAnalyzer,
    "ssti": SstiAnalyzer,
    "ldap_injection": LdapInjectionAnalyzer,
    "mass_assignment": MassAssignmentAnalyzer,
    "race_condition": RaceConditionAnalyzer,
    "secrets": SecretsAnalyzer,
    "crypto": CryptoAnalyzer,
    "dependency": DependencyAnalyzer,
    "sensitive_data": SensitiveDataAnalyzer,
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
        if getattr(a, "scope", None) == "repo":
            findings.extend(a.analyze(ctx))
        else:
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
