#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run deterministic matrix analyzer fixtures.

Usage:
  cd codeaudit
  python3 -m matrix.tests.run_fixtures --all
  python3 -m matrix.tests.run_fixtures --vulnclass authz
  python3 -m matrix.tests.run_fixtures --vulnclass authz --case basic --rebuild

No PostgreSQL and no LLM are used. The JavaParser callgraph sidecar is compiled
on first use if CallGraphDump.class is missing.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from matrix.context import AnalysisContext
from matrix.run import ANALYZERS
from matrix.tests.compare import compare

HERE = Path(__file__).resolve()
CODEAUDIT = HERE.parents[2]
TESTS = HERE.parent
FIXTURES = TESTS / "fixtures"
CACHE = TESTS / ".cache"
CALLGRAPH = CODEAUDIT / "tools" / "callgraph"
SIDECAR_CLASS = CALLGRAPH / "CallGraphDump.class"
SIDECAR_SRC = CALLGRAPH / "CallGraphDump.java"


def _die(msg):
    print("[ERROR] " + msg, file=sys.stderr)
    raise SystemExit(2)


def ensure_sidecar():
    if SIDECAR_CLASS.exists() and SIDECAR_CLASS.stat().st_mtime >= SIDECAR_SRC.stat().st_mtime:
        return
    javac = shutil.which("javac")
    if not javac:
        _die("javac not found; install JDK 8+ or compile codeaudit/tools/callgraph/CallGraphDump.java")
    jars = sorted(str(p) for p in (CALLGRAPH / "lib").glob("*.jar"))
    if not jars:
        _die("callgraph lib jars not found: " + str(CALLGRAPH / "lib"))
    cp = os.pathsep.join(jars)
    print("[sidecar] compiling CallGraphDump.java")
    subprocess.check_call([javac, "-cp", cp, "CallGraphDump.java"], cwd=str(CALLGRAPH))


def _source_mtime(root):
    latest = 0.0
    for path in root.rglob("*.java"):
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            pass
    return latest


def build_graph(case_dir, vulnclass, case_name, rebuild=False):
    out = CACHE / vulnclass / case_name / "graph.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    stale = not out.exists() or _source_mtime(case_dir) > out.stat().st_mtime
    if rebuild or stale:
        cmd = [
            sys.executable,
            "-m",
            "matrix.graph.build",
            str(case_dir),
            str(out),
        ]
        if rebuild or stale:
            cmd.append("--rebuild")
        print("[graph] %s/%s" % (vulnclass, case_name))
        proc = subprocess.run(
            cmd, cwd=str(CODEAUDIT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        if proc.returncode != 0:
            text = proc.stdout.decode("utf-8", "replace")
            raise RuntimeError("graph build failed:\n" + text[-4000:])
    return out


def load_cases(vulnclass=None, case=None):
    cases = []
    for expected_path in sorted(FIXTURES.rglob("expected.json")):
        case_dir = expected_path.parent
        if case_dir.name.startswith("."):
            continue
        try:
            data = json.loads(expected_path.read_text(encoding="utf-8"))
        except Exception as exc:
            _die("invalid expected.json %s: %s" % (expected_path, exc))
        vc = data.get("vulnclass") or case_dir.parent.name
        name = case_dir.name
        if vulnclass and vc != vulnclass:
            continue
        if case and name != case:
            continue
        cases.append((vc, name, case_dir, data))
    return cases


def run_case(vulnclass, name, case_dir, expected, rebuild=False):
    graph_path = build_graph(case_dir, vulnclass, name, rebuild=rebuild)
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    ctx = AnalysisContext(graph, root=str(case_dir))
    cls = ANALYZERS.get(vulnclass)
    if not cls:
        raise RuntimeError("unknown analyzer: " + vulnclass)
    analyzer = cls()
    scope = expected.get("scope") or "endpoint"
    if scope == "repo" or getattr(analyzer, "scope", None) == "repo":
        findings = analyzer.analyze(ctx)
    else:
        findings = []
        for ep in ctx.endpoints():
            findings.extend(analyzer.analyze(ep, ctx))
    issues = compare(expected, findings)
    return issues, findings, graph


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="run all fixtures (default when no filter)")
    ap.add_argument("--vulnclass", help="only one vulnclass")
    ap.add_argument("--case", help="only one case name")
    ap.add_argument("--rebuild", action="store_true", help="force graph rebuild")
    ap.add_argument("--list", action="store_true", help="list fixtures and exit")
    ap.add_argument("--json", action="store_true", help="print machine-readable report")
    args = ap.parse_args()

    cases = load_cases(args.vulnclass, args.case)
    if args.list:
        for vc, name, _, _ in cases:
            print("%s/%s" % (vc, name))
        return 0
    if not cases:
        _die("no fixtures matched; expected codeaudit/matrix/tests/fixtures/**/expected.json")

    ensure_sidecar()

    started = time.time()
    report = []
    failed = 0
    for vc, name, case_dir, expected in cases:
        label = "%s/%s" % (vc, name)
        try:
            issues, findings, graph = run_case(vc, name, case_dir, expected, rebuild=args.rebuild)
            ok = not issues
            if args.json:
                report.append(
                    {
                        "case": label,
                        "ok": ok,
                        "issues": issues,
                        "findings": len(findings),
                        "endpoints": len(graph.get("endpoints") or []),
                    }
                )
            else:
                print("%s %s (%d findings)" % ("[PASS]" if ok else "[FAIL]", label, len(findings)))
                for issue in issues:
                    print("       - " + issue)
            if not ok:
                failed += 1
        except Exception as exc:
            failed += 1
            if args.json:
                report.append({"case": label, "ok": False, "issues": [str(exc)]})
            else:
                print("[FAIL] %s" % label)
                print("       - " + str(exc).replace("\n", "\n         "))

    elapsed = time.time() - started
    if args.json:
        print(json.dumps({"ok": failed == 0, "failed": failed, "total": len(cases),
                          "seconds": round(elapsed, 2), "cases": report},
                         ensure_ascii=False, indent=1))
    else:
        print("")
        print("total=%d passed=%d failed=%d seconds=%.1f" % (
            len(cases), len(cases) - failed, failed, elapsed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
