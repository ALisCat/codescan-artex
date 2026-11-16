#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4 绑定：findings.json → cells.json / tasks.json / report.json

状态机：
  possible  → 派发（按结构信号排序）
  unknown   → 默认不派，--include-unknown 时最低优先级
  impossible→ 不派，带结构证据

不做守卫排除；guards_seen 只进 hints。
"""
import argparse
import importlib.util
import json
from pathlib import Path

from .analyzers.base import POSSIBLE, IMPOSSIBLE, UNKNOWN

VULN_CN = {
    "file-upload": "文件上传", "path-traversal": "路径穿越", "sql-injection": "SQL 注入",
    "command-exec": "命令/表达式注入", "ssrf": "SSRF", "deserialization": "不安全反序列化",
    "xss": "XSS", "authz": "越权", "authn": "认证/回调",
}
VULN_BASE = {"command-exec": 9, "deserialization": 9, "authn": 14, "file-upload": 8,
             "sql-injection": 7, "path-traversal": 7, "ssrf": 6, "authz": 6, "xss": 3}


def _load_cellgen():
    tools = Path(__file__).resolve().parents[1] / "tools"
    spec = importlib.util.spec_from_file_location("cellgen", tools / "cellgen.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CHECKLISTS = dict(_load_cellgen().CHECKLIST)
CHECKLISTS["authn"] = [
    "认证主体从哪里来（token / session / signature / principal）",
    "签名/HMAC/时间戳/nonce 是否校验，是否有重放保护",
    "回调/登录/密码重置是否允许匿名调用",
    "校验逻辑是否真的在请求路径上执行（拦截器/注解/切面是否注册）",
]


def _site_depth(endpoint, site):
    """sink 在 flow 中的位置：0=handler，越大越深。"""
    file, line = site.get("file"), site.get("line")
    for i, step in enumerate(endpoint.get("flow", [])):
        if step.get("file") != file:
            continue
        if step.get("kind") == "dao":
            if step.get("line") == line:
                return i
            continue
        if (step.get("line") or 0) <= (line or 0) <= (step.get("end") or step.get("line") or 0):
            return i
    return 9


def _priority(endpoint, finding):
    vuln = finding["vulnclass"]
    if finding["state"] == UNKNOWN:
        return 1
    base = VULN_BASE.get(vuln, 5)
    ev = finding.get("evidence") or {}
    sites = ev.get("sites") or ev.get("sql_sites") or ev.get("resource_accesses") or []
    depth = min([_site_depth(endpoint, s) for s in sites] or [9])
    direct = 6 if depth == 0 else (3 if depth <= 3 else 0)
    p = base + direct + min(3, len(sites))
    if vuln == "authz" and endpoint.get("params"):
        p += 4
    if not (ev.get("has_input", True)):
        p -= 2
    return max(1, p)


def _bucket(p, state):
    if state == UNKNOWN:
        return "U"
    if p >= 20:
        return "P0"
    if p >= 14:
        return "P1"
    return "P2"


def _task_id(endpoint, vuln):
    return "%s:%s" % (endpoint["url"], vuln)


def _direction(endpoint, vuln):
    if vuln == "authn":
        return "审计 %s %s 的「%s」风险（结构上存在认证/回调入口）" % (
            endpoint["method"], endpoint["url"], VULN_CN.get(vuln, vuln))
    return "审计 %s %s 的「%s」风险（结构上存在 sink/资源访问）" % (
        endpoint["method"], endpoint["url"], VULN_CN.get(vuln, vuln))


def _render_task(task):
    e = task["endpoint"]
    h = task["hints"]
    lines = ["【任务】" + task["direction"], ""]
    lines.append("【结构流程】")
    for i, s in enumerate(h.get("flow", [])[:12], 1):
        lines.append("  %d. %s @ %s:%s" % (i, s.get("name") or s.get("cls") or "?", s.get("file"), s.get("line")))
    lines.append("")
    lines.append("【sink / 资源访问】")
    for s in h.get("sites", [])[:8]:
        lines.append("  - %s @ %s:%s" % (s.get("api") or s.get("method") or s.get("kind"), s.get("file"), s.get("line")))
        if s.get("raw_signals"):
            lines.append("    raw: " + ", ".join(s["raw_signals"]))
        if s.get("parameterized_signals"):
            lines.append("    parameterized: " + ", ".join(s["parameterized_signals"]))
        if s.get("sql"):
            where = ""
            if s.get("sql_file"):
                where = "  [SQL @ %s:%s]" % (s.get("sql_file"), s.get("sql_line"))
            lines.append("    SQL:" + where + " " + s["sql"].replace("\n", " ")[:300])
    lines.append("")
    am = h.get("authz_model")
    if am:
        lines.append("【授权判定模型（语义扫描，名字无关）】")
        p = am.get("principal")
        if p:
            lines.append("  principal: %s (%s) @ %s:%s" % (p.get("var"), p.get("source"), p.get("file"), p.get("line")))
        r = am.get("resource")
        if r:
            lines.append("  resource : %s %s @ %s:%s" % (r.get("type"), r.get("identifier"), r.get("file"), r.get("line")))
        for d in am.get("decisions", [])[:10]:
            lines.append("  - %s: %s @ %s:%s%s" % (
                d.get("kind"), d.get("rule"), d.get("file"), d.get("line"),
                (" [target %s:%s]" % (d.get("target_file"), d.get("target_line"))) if d.get("target_file") and d.get("target_file") != d.get("file") else ""))
        lines.append("  required: %s" % ", ".join(am.get("required") or []))
        lines.append("  gaps    : %s" % (", ".join(am.get("gaps") or []) or "none"))
        sp = am.get("search_policy") or {}
        lines.append("  search  : allow=%s budget=%s kinds=%s" % (
            sp.get("allow_global_search"), sp.get("search_budget"),
            ",".join(sp.get("search_kinds") or []) or "-"))
        if sp.get("search_patterns"):
            lines.append("            patterns=" + " | ".join(sp["search_patterns"]))
        for u in am.get("unknowns", [])[:5]:
            lines.append("  unknown : " + u)
    an = h.get("authn_model")
    if an:
        lines.append("【认证/回调判定模型】")
        lines.append("  kind    : %s" % (an.get("endpoint_kind") or "-"))
        for d in an.get("decisions", [])[:10]:
            lines.append("  - %s: %s @ %s:%s" % (
                d.get("kind"), d.get("rule"), d.get("file"), d.get("line")))
        lines.append("  required: %s" % ", ".join(an.get("required") or []))
        lines.append("  gaps    : %s" % (", ".join(an.get("gaps") or []) or "none"))
        sp = an.get("search_policy") or {}
        lines.append("  search  : allow=%s budget=%s kinds=%s" % (
            sp.get("allow_global_search"), sp.get("search_budget"),
            ",".join(sp.get("search_kinds") or []) or "-"))
        if sp.get("search_patterns"):
            lines.append("            patterns=" + " | ".join(sp["search_patterns"]))
        for u in an.get("unknowns", [])[:5]:
            lines.append("  unknown : " + u)
    gh = h.get("guard_helpers") or []
    if gh:
        lines.append("  guard_helpers:")
        for g in gh[:8]:
            lines.append("    - %s %s @ %s:%s (resolved=%s)" % (
                g.get("kind"), g.get("method"), g.get("target_file") or g.get("call_file"),
                g.get("target_line") or g.get("call_line"), g.get("resolved")))
    if not am and not an:
        lines.append("【守卫线索（仅供判断，不代表安全）】")
        for g in h.get("guards_seen", [])[:8]:
            lines.append("  - %s @ %s:%s" % (g.get("text") or g.get("kind"), g.get("file"), g.get("line")))
    lines.append("")
    lines.append("【要求】")
    lines.append("- 结构证据只说明“可能”，请独立判断可达性、参数可控、白名单/校验是否有效")
    lines.append("- confirmed：文件:行号 + 代码片段 + 触发条件")
    lines.append("- clean：正向证据（哪一行做了什么校验）")
    lines.append("- needs_more：说明缺什么证据")
    lines.append("- 只做源码静态分析，不运行代码、不发起请求")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("graph")
    ap.add_argument("findings")
    ap.add_argument("out_prefix")
    ap.add_argument("--include-unknown", action="store_true")
    args = ap.parse_args()

    graph = json.load(open(args.graph, encoding="utf-8"))
    findings = json.load(open(args.findings, encoding="utf-8"))["findings"]
    by_key = {}
    for f in findings:
        by_key[(f["method"], f["url"], f["vulnclass"])] = f

    endpoints = graph.get("endpoints", [])
    cells, tasks = [], []
    for ep in endpoints:
        for vuln in VULN_CN:
            f = by_key.get((ep["method"], ep["url"], vuln))
            if not f:
                state, evidence, guards, missing = UNKNOWN, {}, [], "analyzer not run"
            else:
                state = f["state"]
                evidence = f.get("evidence") or {}
                guards = f.get("guards_seen") or []
                missing = f.get("missing")
            entry = {
                "endpoint": {
                    "asset_id": 0, "method": ep["method"], "url": ep["url"],
                    "permission": "", "handler": ep.get("handler"),
                    "file": ep.get("file"), "line": ep.get("line"),
                    "params": ep.get("params", []),
                },
                "vulnclass": vuln,
                "state": state,
                "eligibility": ("applicable" if state == POSSIBLE else
                                ("unknown" if state == UNKNOWN else "not_applicable")),
                "signals": [],
                "variant": "structural",
                "sinks": evidence.get("sites") or evidence.get("sql_sites") or evidence.get("resource_accesses") or [],
                "guards": guards,
            }
            if state == POSSIBLE:
                p = _priority(ep, f)
                entry.update({"priority": p, "bucket": _bucket(p, state)})
                task = {
                    "task_id": _task_id(ep, vuln),
                    "asset_ids": [],
                    "direction": _direction(ep, vuln),
                    "vulnclass": vuln,
                    "endpoint": entry["endpoint"],
                    "checklist": CHECKLISTS.get(vuln, []),
                    "hints": {
                        "state": state,
                        "flow": ep.get("flow", [])[:20],
                        "sites": evidence.get("sites") or evidence.get("sql_sites") or evidence.get("resource_accesses") or [],
                        "sinks": evidence.get("sites") or evidence.get("sql_sites") or evidence.get("resource_accesses") or [],
                        "guards_seen": guards,
                        "authz_model": evidence.get("authz_model") if vuln == "authz" else None,
                        "authn_model": evidence.get("authn_model") if vuln == "authn" else None,
                        "guard_helpers": evidence.get("guard_helpers") or [],
                        "subtype": evidence.get("subtype"),
                        "cwe": evidence.get("cwe") or [],
                        "tags": evidence.get("tags") or [],
                        "search_policy": (
                            (evidence.get("authz_model") or {}).get("search_policy")
                            if vuln == "authz" else
                            (evidence.get("authn_model") or {}).get("search_policy")
                            if vuln == "authn" else None
                        ),
                        "params": ep.get("params", []),
                        "analyzer": "structural-v2",
                    },
                    "hints_note": "结构上存在 sink/资源访问，不代表漏洞成立；请判断可达性、白名单、校验。",
                    "priority": p,
                    "bucket": _bucket(p, state),
                    "role": "secondary",
                    "related_tasks": [],
                }
                task["prompt"] = _render_task(task)
                tasks.append(task)
            elif state == UNKNOWN:
                entry.update({"priority": 1, "bucket": "U", "reason": missing or "graph incomplete"})
                if args.include_unknown:
                    task = {
                        "task_id": _task_id(ep, vuln), "asset_ids": [],
                        "direction": _direction(ep, vuln) + "（未知，需补充确认）",
                        "vulnclass": vuln, "endpoint": entry["endpoint"],
                        "checklist": CHECKLISTS.get(vuln, []),
                        "hints": {"state": state, "flow": ep.get("flow", [])[:20],
                                  "sites": [], "guards_seen": guards,
                                  "authz_model": evidence.get("authz_model") if vuln == "authz" else None,
                                  "authn_model": evidence.get("authn_model") if vuln == "authn" else None,
                                  "guard_helpers": evidence.get("guard_helpers") or [],
                                  "subtype": evidence.get("subtype"),
                                  "cwe": evidence.get("cwe") or [],
                                  "tags": evidence.get("tags") or [],
                                  "search_policy": (
                                      (evidence.get("authz_model") or {}).get("search_policy")
                                      if vuln == "authz" else
                                      (evidence.get("authn_model") or {}).get("search_policy")
                                      if vuln == "authn" else None
                                  ),
                                  "params": ep.get("params", []), "analyzer": "structural-v2"},
                        "hints_note": "图不完整，可能藏着 sink；请先补链路再判断。",
                        "priority": 1, "bucket": "U", "role": "secondary", "related_tasks": [],
                    }
                    task["prompt"] = _render_task(task)
                    tasks.append(task)
            else:
                entry.update({
                    "priority": 0, "bucket": "NA",
                    "reason": missing or "结构上未发现该类 sink / 资源访问",
                    "trace": evidence.get("sites", [])[:5],
                })
            cells.append(entry)

    # primary/secondary per endpoint
    by_ep = {}
    for t in tasks:
        by_ep.setdefault(t["endpoint"]["url"], []).append(t)
    for url, ts in by_ep.items():
        ts.sort(key=lambda x: -x["priority"])
        for i, t in enumerate(ts):
            t["role"] = "primary" if i == 0 else "secondary"
            t["related_tasks"] = [x["task_id"] for x in ts if x is not t]

    out = Path(args.out_prefix)
    out.parent.mkdir(parents=True, exist_ok=True)
    (out.parent / (out.name + ".cells.json")).write_text(json.dumps(cells, ensure_ascii=False, indent=1), encoding="utf-8")
    (out.parent / (out.name + ".tasks.json")).write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")

    by_state = {}
    for c in cells:
        by_state[c["state"]] = by_state.get(c["state"], 0) + 1
    report = {
        "endpoints": len(endpoints),
        "cells": len(cells),
        "by_state": by_state,
        "tasks": len(tasks),
        "include_unknown": bool(args.include_unknown),
    }
    (out.parent / (out.name + ".report.json")).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
