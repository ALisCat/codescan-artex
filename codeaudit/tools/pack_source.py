#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包源码用于上传，排除评测/标注/构建产物，避免 worker 读到答案。

用法：python3 pack_source.py <源码目录> <输出 zip>
"""
import argparse
import os
import zipfile

EXCLUDE_DIRS = {".git", "target", "build", "node_modules", ".audit", "labels", ".idea", ".vscode"}
EXCLUDE_NAMES = {"GROUND-TRUTH.csv", "ground-truth.csv", "LABELS.csv", "labels.csv"}
EXCLUDE_SUFFIX = (".eval", ".label", ".labels", ".md", ".markdown")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    args = ap.parse_args()
    src = os.path.abspath(args.src)
    n = 0
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, dns, fns in os.walk(src):
            dns[:] = [d for d in dns if d not in EXCLUDE_DIRS]
            for fn in fns:
                if fn in EXCLUDE_NAMES or fn.endswith(EXCLUDE_SUFFIX):
                    continue
                p = os.path.join(dp, fn)
                rel = os.path.relpath(p, src)
                z.write(p, rel)
                n += 1
    print("%s -> %s (%d files)" % (src, args.out, n))


if __name__ == "__main__":
    main()
