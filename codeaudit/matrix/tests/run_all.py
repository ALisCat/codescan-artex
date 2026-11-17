#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot deterministic matrix regression.

Runs:
  1. all analyzer fixtures
  2. demo v1 / v2 / fresh-clinic regression + baseline check

Usage:
  cd codeaudit
  python3 -m matrix.tests.run_all
  python3 -m matrix.tests.run_all --rebuild
  python3 -m matrix.tests.run_all --update-baseline
"""
import argparse
import subprocess
import sys

from matrix.tests.run_fixtures import CODEAUDIT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--no-check", action="store_true")
    args = ap.parse_args()

    fixture_cmd = [sys.executable, "-m", "matrix.tests.run_fixtures", "--all"]
    if args.rebuild:
        fixture_cmd.append("--rebuild")
    print("[1/2] analyzer fixtures")
    if subprocess.call(fixture_cmd, cwd=str(CODEAUDIT)) != 0:
        return 1

    regression_cmd = [sys.executable, "-m", "matrix.tests.run_regression", "--all"]
    if args.rebuild:
        regression_cmd.append("--rebuild")
    if args.update_baseline:
        regression_cmd.append("--update-baseline")
    elif not args.no_check:
        regression_cmd.append("--check")
    print("[2/2] demo regression")
    if subprocess.call(regression_cmd, cwd=str(CODEAUDIT)) != 0:
        return 1
    print("[OK] matrix regression passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
