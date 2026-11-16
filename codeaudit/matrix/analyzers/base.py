#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析器基类与 Finding 约定。

分析器只回答：
  - 流程里有没有该类 sink / 资源访问
  - possible / impossible / unknown
不判断：污点、可达性、白名单、防护、归属是否有效。
"""

POSSIBLE = "possible"
IMPOSSIBLE = "impossible"
UNKNOWN = "unknown"


class Finding(dict):
    """统一结果结构（dict 方便直接序列化）。"""

    @staticmethod
    def make(endpoint, vulnclass, state, evidence=None, guards_seen=None, missing=None):
        return Finding({
            "endpoint_id": endpoint.get("id"),
            "method": endpoint.get("method"),
            "url": endpoint.get("url"),
            "vulnclass": vulnclass,
            "state": state,
            "evidence": evidence or {},
            "guards_seen": guards_seen or [],
            "missing": missing,
        })


class Analyzer:
    vulnclass = ""

    def analyze(self, endpoint, ctx):
        raise NotImplementedError
