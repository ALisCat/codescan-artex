#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M5：把 binder 输出转成平台导入体。

映射：
  possible   → eligibility=applicable  （平台 status=pending，会被 seed）
  unknown    → eligibility=unverified  （平台不派，UI 显示未知）
  impossible → eligibility=not_applicable
"""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cells")
    ap.add_argument("tasks")
    ap.add_argument("out")
    ap.add_argument("--seed", action="store_true", default=True)
    args = ap.parse_args()

    cells = json.load(open(args.cells, encoding="utf-8"))
    tasks = json.load(open(args.tasks, encoding="utf-8"))
    by_id = {t["task_id"]: t for t in tasks}

    rows = []
    for c in cells:
        ep = c["endpoint"]
        key = "%s %s:%s" % (ep.get("method", ""), ep["url"], c["vulnclass"])
        state = c["state"]
        t = by_id.get(key)
        if state == "possible" and t:
            row = {
                "task_id": key,
                "endpoint": {"method": ep["method"], "url": ep["url"], "asset_id": 0},
                "vulnclass": c["vulnclass"],
                "eligibility": "applicable",
                "direction": t["direction"],
                "priority": t["priority"],
                "bucket": t["bucket"],
                "checklist": t.get("checklist") or [],
                "hints": t.get("hints") or {},
                "hints_note": t.get("hints_note") or "",
                "reason": "",
                "trace": [],
            }
        elif state == "unknown":
            hints = c.get("hints") or {"state": "unknown"}
            row = {
                "task_id": key,
                "endpoint": {"method": ep["method"], "url": ep["url"], "asset_id": 0},
                "vulnclass": c["vulnclass"],
                "eligibility": "unverified",
                "direction": "未知（图不完整）：审计 %s %s 的「%s」风险" % (
                    ep["method"], ep["url"], c["vulnclass"]),
                "priority": 1,
                "bucket": "U",
                "checklist": [],
                "hints": hints,
                "hints_note": "图不完整，可能藏着 sink；需要补充链路后再判断。",
                "reason": c.get("reason") or "graph incomplete",
                "trace": [],
            }
        else:
            row = {
                "task_id": key,
                "endpoint": {"method": ep["method"], "url": ep["url"], "asset_id": 0},
                "vulnclass": c["vulnclass"],
                "eligibility": "not_applicable",
                "direction": "不适用：" + (c.get("reason") or "结构上未发现该类 sink"),
                "priority": 0,
                "bucket": "N/A",
                "checklist": [],
                "hints": c.get("hints") or {},
                "hints_note": "",
                "reason": c.get("reason") or "结构上未发现该类 sink",
                "trace": c.get("trace") or [],
            }
        rows.append(row)

    body = {"tasks": rows, "seed": True}
    Path(args.out).write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print("rows=%d states=%s dispatchable=%d" % (
        len(rows),
        dict(Counter(r["eligibility"] for r in rows)),
        sum(1 for r in rows if r["eligibility"] == "applicable"),
    ))


if __name__ == "__main__":
    main()
