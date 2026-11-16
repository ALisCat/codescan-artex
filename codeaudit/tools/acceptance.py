#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
派发清单验收（方向式）

矩阵只负责"派方向"，不负责"判正误"。因此验收看三件事：

  R1 方向召回      已知漏洞对应的 (接口,类型) 必须被派出去
  R2 指针有效性    hints 里引用的 file:line 必须真实存在，且该行确实包含所标注的 API
  R3 派发成本      任务总数不超过预算（默认 120）

用法：python3 acceptance.py <tasks.json> <src_root> [budget]
"""
import json, sys, os, re

TASKS = sys.argv[1] if len(sys.argv) > 1 else '/tmp/opencode/java/tasks.json'
SRC   = sys.argv[2] if len(sys.argv) > 2 else '/opt/codescan/data/tasks/1/source'
BUDGET= int(sys.argv[3]) if len(sys.argv) > 3 else 120

tasks = json.load(open(TASKS))

KNOWN = [
    ('/sqli/jdbc/vuln', 'sql-injection'), ('/sqli/jdbc/ps/vuln', 'sql-injection'),
    ('/sqli/mybatis/vuln01', 'sql-injection'), ('/sqli/mybatis/vuln02', 'sql-injection'),
    ('/sqli/mybatis/orderby/vuln03', 'sql-injection'),
    ('/rce/runtime/exec', 'command-exec'), ('/rce/ProcessBuilder', 'command-exec'),
    ('/rce/jscmd', 'command-exec'), ('/rce/vuln/yarm', 'command-exec'),
    ('/rce/groovy', 'command-exec'),
    ('/spel/vuln1', 'command-exec'), ('/spel/vuln2', 'command-exec'),
    ('/codeinject', 'command-exec'), ('/codeinject/host', 'command-exec'),
    ('/ssti/velocity', 'command-exec'), ('/vuln1', 'command-exec'),
    ('/deserialize/rememberMe/vuln', 'deserialization'),
    ('/shiro/deserialize', 'deserialization'),
    ('/file/upload', 'file-upload'), ('/file/upload/picture', 'file-upload'),
    ('/path_traversal/vul', 'path-traversal'),
    ('/ssrf/urlConnection/vuln', 'ssrf'), ('/ssrf/hutool/vuln', 'ssrf'),
]

dispatched = {}
for t in tasks:
    dispatched.setdefault(t['endpoint']['url'], set()).add(t['vulnclass'])

print("=" * 72)
print("R1 方向召回（漏派 = 静默漏报，最严重）")
print("=" * 72)
miss = [(u, v) for u, v in KNOWN if v not in dispatched.get(u, set())]
for u, v in miss:
    print(f"  ❌ 漏派 {u} × {v}")
ok = len(KNOWN) - len(miss)
print(f"  召回 {ok}/{len(KNOWN)} = {ok/len(KNOWN)*100:.0f}%")
r1 = ok == len(KNOWN)

print()
print("=" * 72)
print("R2 指针有效性（线索不能指错地方）")
print("=" * 72)
total = bad = 0
for t in tasks:
    for sk in t['hints'].get('sinks', []):
        total += 1
        path = os.path.join(SRC, sk['file'])
        ln = sk.get('line', -1)
        api = sk.get('api', '')
        ids = re.findall(r'[A-Za-z_$][\w$]*', api)
        token = ids[-1] if ids else ''
        try:
            lines = open(path, encoding='utf-8', errors='replace').read().split('\n')
            src_line = lines[ln-1] if 0 < ln <= len(lines) else ''
        except Exception:
            src_line = ''
        if 'MyBatis' in api:
            ok_line = ('${' in src_line) or src_line.strip().startswith('<select') or src_line.strip().startswith('<update') or src_line.strip().startswith('<insert')
        elif api.strip() == '数据访问':
            ok_line = bool(src_line.strip())
        else:
            ok_line = bool(src_line) and (not token or token.lower() in src_line.lower())
        if not ok_line:
            bad += 1
            if bad <= 8:
                print(f"  ❌ {sk['file']}:{ln} 标注 {api}，实际: {src_line.strip()[:70]}")
print(f"  有效 {total-bad}/{total} = {(total-bad)/max(1,total)*100:.1f}%")
r2 = bad == 0

print()
print("=" * 72)
print("R3 派发成本")
print("=" * 72)
print(f"  任务总数 {len(tasks)}  (预算 {BUDGET})")
from collections import Counter
print("  分档:", dict(Counter(t['bucket'] for t in tasks)))
r3 = len(tasks) <= BUDGET

print()
print("=" * 72)
print(f"结果：{'✅ PASS' if (r1 and r2 and r3) else '❌ FAIL'}   "
      f"(R1={'PASS' if r1 else 'FAIL'} R2={'PASS' if r2 else 'FAIL'} R3={'PASS' if r3 else 'FAIL'})")
print("=" * 72)
sys.exit(0 if (r1 and r2 and r3) else 1)
