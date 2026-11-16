#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""demo 评测：用 ground-truth.csv 校验矩阵的召回与误派。

用法：python3 demo_eval.py <cells.json/tasks.json 目录> <ground-truth.csv>

判定口径：
  - dispatched = tasks.json 里的 (method,url,vulnclass) → 真正会消耗 worker
  - 召回 = ground-truth 里 vuln 且被 dispatched 的比例（漏派=静默漏报）
  - 误派 = dispatched 中 label 不是 vuln 的比例（safe/na/未标注）
  - unlabeled = 有派单但 ground truth 没写的格子（应尽量避免）
"""
import csv, json, os, sys
from collections import Counter, defaultdict

OUT = sys.argv[1]
GT = sys.argv[2]
tasks = json.load(open(os.path.join(OUT, 'tasks.json'), encoding='utf-8'))
cells = json.load(open(os.path.join(OUT, 'cells.json'), encoding='utf-8'))

labels = {}
for r in csv.DictReader(open(GT, encoding='utf-8')):
    labels[(r['endpoint'], r['method'], r['vulnclass'])] = r['verdict']

dispatched = set()
for t in tasks:
    ep = t['endpoint']
    dispatched.add((ep['url'], ep['method'], t['vulnclass']))

# vuln 口径
vulns = {k for k, v in labels.items() if v == 'vuln'}
hit = {k for k in vulns if k in dispatched}
miss = sorted(vulns - hit)

# 误派口径
false = []
unlabeled = []
for k in dispatched:
    v = labels.get(k)
    if v is None:
        unlabeled.append(k)
    elif v != 'vuln':
        false.append((k, v))

# 未派但结构上 relevant 的 vuln（cells 里 applicable/needs_review）
cell_elig = {(c['endpoint']['url'], c['endpoint']['method'], c['vulnclass']): c['eligibility'] for c in cells}
held = {k for k, v in cell_elig.items() if v == 'hold'}
held_vuln = sorted(k for k in vulns if k in held and k not in dispatched)
unv_vuln = sorted(k for k in vulns if cell_elig.get(k) == 'unverified' and k not in dispatched)

total = len(dispatched)
print(f"== {os.path.basename(os.path.dirname(GT)) or GT} ==")
print(f"  ground truth: vuln={len(vulns)}  safe/na={sum(1 for v in labels.values() if v != 'vuln')}")
print(f"  dispatched={total}  applicable={sum(1 for c in cells if c['eligibility']=='applicable')}  "
      f"needs_review={sum(1 for c in cells if c['eligibility']=='needs_review')}  "
      f"unverified={sum(1 for c in cells if c['eligibility']=='unverified')}")
print(f"  held={len(held)}  未验证={sum(1 for v in cell_elig.values() if v=='unverified')}")
print(f"  召回: {len(hit)}/{len(vulns)} = {len(hit)/max(1,len(vulns))*100:.0f}%")
for k in miss:
    tag = 'hold（矩阵可见）' if k in held else ('unverified' if k in unv_vuln else 'N/A')
    print(f"    ❌ 漏派 {k[1]} {k[0]} × {k[2]}  ({tag})")
false_rate = len(false) / max(1, total) * 100
print(f"  误派: {len(false)}/{total} = {false_rate:.0f}%")
by_type = Counter(k[2] for k, _ in false)
print(f"    按类型: {dict(by_type)}")
for (k, v) in sorted(false):
    print(f"    ⚠️  {k[1]:5s} {k[0]:32s} {k[2]:14s} label={v}")
if unlabeled:
    print(f"  未标注但被派: {len(unlabeled)}")
    for k in sorted(unlabeled):
        print(f"    ❓ {k[1]} {k[0]} × {k[2]}")
print()
