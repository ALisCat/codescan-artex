#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把生成器的 cells.json（完整矩阵，含 not_applicable）转成导入体。

用法: python3 mkfull.py <cells.json> <tasks.json> <out.json>
cell_key 与 tasks.json 保持一致：<asset_id 或 url>:<vulnclass>
"""
import json, sys

cells_path, tasks_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
cells = json.load(open(cells_path))
tasks = json.load(open(tasks_path))

# tasks.json 提供 direction/checklist/hints（只有要派的格子）
tm = {}
for t in tasks:
    ep = t.get("endpoint") or {}
    key = f"{ep.get('asset_id') or ep.get('url')}:{t.get('vulnclass')}"
    tm[key] = t

out = []
for c in cells:
    ep = c.get("endpoint") or {}
    vuln = c.get("vulnclass")
    aid = ep.get("asset_id")
    key = f"{aid or ep.get('url')}:{vuln}"
    elig = c.get("eligibility")
    t = tm.get(key)
    row = {
        "task_id": key,
        "endpoint": {"method": ep.get("method") or "", "url": ep.get("url") or "", "asset_id": aid or 0},
        "vulnclass": vuln,
        "eligibility": elig,
    }
    if elig == "hold":
        row.update({
            "direction": "有守卫（暂不派）：" + (c.get("reason") or ""),
            "reason": c.get("reason") or "",
            "trace": c.get("trace") or [],
            "priority": 0,
            "bucket": "HOLD",
            "checklist": [],
            "hints": {},
            "hints_note": "",
            "hold": True,
        })
    elif elig == "unverified":
        row.update({
            "direction": "未验证：" + (c.get("reason") or ""),
            "reason": c.get("reason") or "",
            "trace": c.get("trace") or [],
            "priority": 0,
            "bucket": "U",
            "checklist": [],
            "hints": {},
            "hints_note": "",
        })
    elif elig == "not_applicable":
        row.update({
            "direction": "不适用：" + (c.get("reason") or ""),
            "reason": c.get("reason") or "",
            "trace": c.get("trace") or [],
            "priority": 0,
            "bucket": "N/A",
            "checklist": [],
            "hints": {},
            "hints_note": "",
        })
    else:
        if not t:
            # 低置信且未派单：保留在矩阵里可见（status=hold），不进入 worker 队列。
            row.update({
                "direction": "低置信未派：" + (c.get("reason") or "命名/注释信号不足"),
                "reason": (c.get("reason") or "命名/注释信号不足") + "；默认不派单（矩阵可见）",
                "trace": c.get("trace") or [],
                "priority": 0,
                "bucket": "HOLD",
                "checklist": [],
                "hints": {},
                "hints_note": "",
                "hold": True,
            })
        else:
            row.update({
                "direction": (t or {}).get("direction") or f"审计 {ep.get('method','')} {ep.get('url','')} 的「{vuln}」风险",
                "priority": c.get("priority", 0),
                "bucket": c.get("bucket", ""),
                "checklist": (t or {}).get("checklist") or [],
                "hints": (t or {}).get("hints") or {},
                "hints_note": (t or {}).get("hints_note") or "",
                "reason": "",
                "trace": [],
            })
    out.append(row)

json.dump({"tasks": out, "seed": False}, open(out_path, "w"), ensure_ascii=False)
print(f"  cells={len(cells)}  要派={len(tm)}  na={sum(1 for r in out if r['eligibility']=='not_applicable')}  -> {out_path}")
