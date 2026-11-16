#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""矩阵漏判扫描：找出"代码里确实存在 sink，但矩阵判了 N/A"的 (接口,类型)。

不做污点判定（污点判定正是被检查的对象），只做结构可达：
从 handler 出发按接收者类型解析调用链，收集所有 sink 命中，
再和 cells.json 的 eligibility 对比。

用法：python3 gapscan.py <源码目录> <cells.json>
输出按 (接口,类型) 聚合，附 sink 位置，供人工判断。
"""
import importlib.util, json, re, sys
from collections import deque, defaultdict

spec = importlib.util.spec_from_file_location("cg", "/tmp/opencode/cellgen.py")
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)

ROOT = sys.argv[1]
CELLS = json.load(open(sys.argv[2], encoding="utf-8"))
C.ROOT = ROOT

clean, masked, raws, xml_map, ann_map, idx, proj = C.parse_project(ROOT)
eps = C.endpoints(clean, masked, idx, raws)
pub = C.load_permission(ROOT)
policy = C.load_auth_policy(clean)

# endpoint → 所属类
owner = {}
for cls, mms in proj["methods"].items():
    for nm, defs in mms.items():
        for d in defs:
            owner[(d["file"], nm, d.get("bline", d["line"]))] = cls
            owner.setdefault((d["file"], nm), cls)

elig = {}
for c in CELLS:
    ep = c.get("endpoint") or {}
    elig[(ep.get("method"), ep.get("url"), c.get("vulnclass"))] = c.get("eligibility")

rows = []
for ep in eps:
    ep["cls"] = owner.get((ep["file"], ep["handler"], ep.get("bline", -1))) or owner.get(
        (ep["file"], ep["handler"]), ""
    )
    seen = set()
    q = deque([(ep["handler"], ep["body"], ep["file"], ep["line"], 0, ep["params"], ep["cls"])])
    blocks = []
    while q:
        nm, body, file, line, d, params, cls = q.popleft()
        if (nm, file, d) in seen:
            continue
        seen.add((nm, file, d))
        blocks.append((nm, file, line, body, params, cls))
        if d >= 4:
            continue
        for callee, args, off in C.collect_calls(body):
            defs, how = C.resolve_callee(body, off, callee, params, proj, cls)
            if not defs:
                cand = idx.get(callee, [])
                if len(cand) == 1:
                    defs = cand
            for dn in defs[:3]:
                q.append((callee, dn["body"], dn["file"], dn["line"], d + 1, dn["params"], dn.get("cls", "")))

    found = defaultdict(list)
    for nm, file, line, body, params, cls in blocks:
        for vuln, pat in C.SINK_PAT.items():
            for m in re.finditer(pat, body):
                args = C.tail_args(body, m.start())
                ats = C.arg_types_of(args, body, m.start(), params, proj, cls)
                if not C.sink_signature_ok(vuln, m.group(0), ats):
                    continue
                loc = (line or 0) + body[: m.start()].count("\n")
                found[vuln].append((nm, C.rel(file), loc, m.group(0).strip()[:40], args.strip()[:70]))
        for callee, args, off in C.collect_calls(body):
            if callee in xml_map and "${" in xml_map[callee][0]:
                found["sql-injection"].append((nm, C.rel(xml_map[callee][1]), xml_map[callee][2], "MyBatis ${} " + callee, args.strip()[:70]))
            if callee in ann_map:
                for t, f, l in ann_map[callee]:
                    if "${" in t:
                        found["sql-injection"].append((nm, C.rel(f), l, "MyBatis @Select ${} " + callee, args.strip()[:70]))

    for vuln, hits in found.items():
        e = elig.get((ep["http"], ep["url"], vuln))
        if e == "not_applicable":
            rows.append((ep["http"], ep["url"], vuln, hits[:4]))

print(f"源码: {ROOT}")
print(f"扫描到 {len(rows)} 个『有 sink 但判 N/A』的 (接口,类型)\n")
for method, url, vuln, hits in sorted(rows):
    print(f"[{vuln:14s}] {method:5s} {url}")
    for nm, f, l, api, args in hits:
        print(f"    {f}:{l}  {nm}()  {api}  args={args}")
    print()
