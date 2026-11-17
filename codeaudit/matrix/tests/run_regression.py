#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Demo regression for the structural matrix.

This is deliberately separate from worker/LLM evaluation: it only checks the
deterministic graph + analyzer + matrix-dispatch signal layer.

Usage:
  cd codeaudit
  python3 -m matrix.tests.run_regression --all
  python3 -m matrix.tests.run_regression --demo v1 --rebuild
  python3 -m matrix.tests.run_regression --all --update-baseline
  python3 -m matrix.tests.run_regression --all --check
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from matrix.context import AnalysisContext
from matrix.run import ANALYZERS
from matrix.tests.run_fixtures import ensure_sidecar, CODEAUDIT, TESTS

DEMO = CODEAUDIT / "demo"
LABELS = DEMO / "labels"
CACHE = TESTS / ".cache" / "regression"
BASELINE = TESTS / "BASELINE.json"


def _source_mtime(root):
    latest = 0.0
    for path in root.rglob("*.java"):
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            pass
    return latest


def build_graph(source, name, rebuild=False):
    out = CACHE / name / "graph.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    stale = not out.exists() or _source_mtime(source) > out.stat().st_mtime
    if rebuild or stale:
        cmd = [sys.executable, "-m", "matrix.graph.build", str(source), str(out)]
        if rebuild or stale:
            cmd.append("--rebuild")
        print("[graph] %s" % name)
        proc = subprocess.run(
            cmd, cwd=str(CODEAUDIT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stdout.decode("utf-8", "replace")[-4000:])
    return out


def run_findings(source, graph_path):
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    ctx = AnalysisContext(graph, root=str(source))
    findings = []
    for name, cls in ANALYZERS.items():
        analyzer = cls()
        if getattr(analyzer, "scope", None) == "repo":
            findings.extend(analyzer.analyze(ctx))
        else:
            for endpoint in ctx.endpoints():
                findings.extend(analyzer.analyze(endpoint, ctx))
    return graph, findings


def load_labels(path):
    out = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            key = (row.get("method", "").upper(), row.get("endpoint", ""), row.get("vulnclass", ""))
            out[key] = row
    return out


def metrics(labels, findings):
    by_key = {}
    for f in findings:
        key = ((f.get("method") or "").upper(), f.get("url") or "", f.get("vulnclass") or "")
        by_key.setdefault(key, f)
    result = {
        "labels": len(labels),
        "vuln_total": 0,
        "vuln_possible": 0,
        "vuln_missing": [],
        "safe_total": 0,
        "safe_possible": 0,
        "unknown_total": 0,
        "na_total": 0,
        "na_possible": 0,
        "false_dispatch": 0,
    }
    for key, label in labels.items():
        verdict = (label.get("verdict") or "").lower()
        f = by_key.get(key)
        state = f.get("state") if f else "missing"
        if state == "unknown" or state == "missing":
            result["unknown_total"] += 1
        if verdict == "vuln":
            result["vuln_total"] += 1
            if state == "possible":
                result["vuln_possible"] += 1
            else:
                result["vuln_missing"].append("%s %s:%s -> %s" % (key[0], key[1], key[2], state))
        elif verdict == "na":
            result["na_total"] += 1
            if state == "possible":
                result["na_possible"] += 1
                result["false_dispatch"] += 1
        else:
            result["safe_total"] += 1
            if state == "possible":
                result["safe_possible"] += 1
                result["false_dispatch"] += 1
    result["vuln_recall"] = (
        round(float(result["vuln_possible"]) / result["vuln_total"], 4)
        if result["vuln_total"] else 1.0
    )
    result["safe_dispatch_rate"] = (
        round(float(result["safe_possible"]) / result["safe_total"], 4)
        if result["safe_total"] else 0.0
    )
    result["na_dispatch_rate"] = (
        round(float(result["na_possible"]) / result["na_total"], 4)
        if result["na_total"] else 0.0
    )
    return result


def summarize_findings(findings):
    out = {"possible": 0, "impossible": 0, "unknown": 0, "total": len(findings)}
    for f in findings:
        state = f.get("state")
        if state in out:
            out[state] += 1
    return out


def run_demo(name, rebuild=False):
    source = DEMO / name
    if not source.exists():
        raise SystemExit("demo not found: " + str(source))
    graph_path = build_graph(source, name, rebuild=rebuild)
    graph, findings = run_findings(source, graph_path)
    label_path = LABELS / (name + ".csv")
    if label_path.exists():
        m = metrics(load_labels(label_path), findings)
    else:
        m = {"labels": 0, "note": "no label file; matrix summary only"}
    m["endpoints"] = len(graph.get("endpoints") or [])
    m["findings"] = summarize_findings(findings)
    return m


def compare_baseline(current, baseline):
    issues = []
    old = baseline.get("demos") or {}
    for name, now in current.items():
        before = old.get(name) or {}
        for key in ("vuln_total", "vuln_possible", "safe_total", "safe_possible",
                    "na_total", "na_possible", "unknown_total", "false_dispatch"):
            if before.get(key) != now.get(key):
                issues.append("%s.%s baseline=%r current=%r" % (
                    name, key, before.get(key), now.get(key)))
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="run v1 + v2 + fresh-clinic")
    ap.add_argument("--demo", choices=["v1", "v2", "fresh-clinic"], help="run one demo")
    ap.add_argument("--rebuild", action="store_true", help="force graph rebuild")
    ap.add_argument("--update-baseline", action="store_true", help="write BASELINE.json")
    ap.add_argument("--check", action="store_true", help="compare with BASELINE.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    ensure_sidecar()
    names = ["v1", "v2", "fresh-clinic"] if args.all or not args.demo else [args.demo]
    started = time.time()
    current = {}
    for name in names:
        current[name] = run_demo(name, rebuild=args.rebuild)

    if args.update_baseline:
        payload = {
            "generated_by": "matrix.tests.run_regression",
            "demos": current,
        }
        BASELINE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        print("[baseline] wrote " + str(BASELINE))

    issues = []
    if args.check and BASELINE.exists():
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        issues = compare_baseline(current, baseline)

    if args.json:
        print(json.dumps({"results": current, "baseline_issues": issues}, ensure_ascii=False, indent=2))
    else:
        for name, m in current.items():
            if m.get("labels"):
                print("%s: endpoints=%d recall=%s (%d/%d) safe_dispatch=%s (%d/%d) "
                      "na_dispatch=%d unknown=%d false_dispatch=%d" % (
                          name, m["endpoints"], m["vuln_recall"], m["vuln_possible"],
                          m["vuln_total"], m["safe_dispatch_rate"], m["safe_possible"],
                          m["safe_total"], m["na_possible"], m["unknown_total"],
                          m["false_dispatch"]))
                for miss in m.get("vuln_missing") or []:
                    print("  miss: " + miss)
            else:
                print("%s: endpoints=%d findings=%s" % (
                    name, m["endpoints"], m["findings"]))
        print("elapsed=%.1fs" % (time.time() - started))
        if issues:
            for issue in issues:
                print("[baseline] " + issue)
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
