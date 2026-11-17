#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""authn 分析器：认证/签名/回调真实性。

只回答结构上是否存在认证/签名缺口，不判断签名能否绕过、密钥是否泄露。
"""
import re
from pathlib import Path

import yaml

from .base import Analyzer, Finding, POSSIBLE, IMPOSSIBLE, UNKNOWN

CATALOG = Path(__file__).resolve().parents[1] / "catalogs" / "authn.yaml"

REQUIRED = {
    "signature": "signature",
    "replay_protection": "replay_protection",
    "authentication": "authentication",
}


class AuthnAnalyzer(Analyzer):
    vulnclass = "authn"

    def __init__(self):
        self.c = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
        self.callback_re = re.compile("|".join(self.c.get("callback_path") or []))
        self.token_re = re.compile("|".join(self.c.get("token_path") or []))
        self.patterns = {
            "signature": [re.compile(p) for p in self.c.get("signature", [])],
            "replay_protection": [re.compile(p) for p in self.c.get("replay", [])],
            "authentication": [re.compile(p) for p in self.c.get("authentication", [])],
        }

    def _kind(self, endpoint):
        text = "%s %s" % (endpoint.get("url") or "", endpoint.get("handler") or "")
        if self.callback_re.search(text):
            return "callback"
        if self.token_re.search(text):
            return "token"
        return ""

    def _find(self, ctx, endpoint, kind):
        out = []
        flow = [s for s in endpoint.get("flow", []) if s.get("kind") == "method"]
        for i, step in enumerate(flow):
            # 只看入口和认证/回调相关方法，避免把下游出站签名/时间戳当成入站校验。
            name = step.get("name") or ""
            if i > 0:
                if kind == "replay_protection":
                    # 时间戳可能来自出站签名 helper（getAuthHeader），不能算入站重放保护。
                    if not re.search(r"(?i)(callback|notify|pay|refund|token|login|verify)", name):
                        continue
                elif not re.search(r"(?i)(callback|notify|auth|login|token|session|verify|sign|pay|refund)", name):
                    continue
            for pat in self.patterns.get(kind, []):
                for file, line, text in ctx.find(step, pat):
                    out.append({
                        "kind": kind, "file": file, "line": line,
                        "rule": text[:160], "method": step.get("name"),
                    })
        # 去重
        seen, uniq = set(), []
        for d in out:
            key = (d["kind"], d["file"], d["line"], d["rule"])
            if key in seen:
                continue
            seen.add(key)
            uniq.append(d)
        return uniq

    def analyze(self, endpoint, ctx):
        epk = self._kind(endpoint)
        if not epk:
            model = {
                "endpoint_kind": "none", "required": [], "decisions": [],
                "gaps": [], "unknowns": [], "search_policy": {
                    "allow_global_search": False, "search_budget": 2,
                    "search_kinds": [], "search_patterns": [],
                },
            }
            return [Finding.make(endpoint, self.vulnclass, IMPOSSIBLE, {
                "authn_model": model, "scope": "endpoint", "subtype": "not-authn",
            }, [], "not an authentication/callback endpoint")]

        decisions = []
        for kind in ("authentication", "signature", "replay_protection"):
            decisions.extend(self._find(ctx, endpoint, kind))

        required = ["signature", "replay_protection"] if epk == "callback" else ["authentication"]
        observed = {d["kind"] for d in decisions}
        gaps = [k for k in required if k not in observed]

        # 回调类如果没有请求体/参数，结构上仍可能是回调，但证据不足，标记 unknown。
        has_input = bool(endpoint.get("params")) or (endpoint.get("method") in ("POST", "PUT", "PATCH"))
        state = POSSIBLE if has_input else UNKNOWN
        missing = None
        if gaps:
            missing = "缺失认证控制: " + ", ".join(gaps)
            if not has_input:
                missing += "；回调入口没有可见请求参数/请求体"
        elif not has_input:
            missing = "回调入口没有可见请求参数/请求体"

        if "signature" in gaps:
            subtype = "callback-no-signature" if epk == "callback" else "token-no-signature"
        elif "replay_protection" in gaps:
            subtype = "callback-no-replay-protection"
        elif "authentication" in gaps:
            subtype = "token-verification-missing"
        else:
            subtype = "authn-controls-present"

        cwe = []
        if "authentication" in gaps:
            cwe.append("CWE-306")
        if "signature" in gaps:
            cwe.extend(["CWE-306", "CWE-347"])
        if "replay_protection" in gaps:
            cwe.append("CWE-294")

        search_kinds = list(gaps)
        search_pats = []
        for k in search_kinds:
            search_pats.extend(self.c.get("replay" if k == "replay_protection" else k, []))
        model = {
            "endpoint_kind": epk,
            "required": required,
            "decisions": decisions,
            "gaps": gaps,
            "unknowns": [] if state == POSSIBLE else [missing or "authn evidence incomplete"],
            "search_policy": {
                "allow_global_search": bool(search_kinds),
                "search_budget": 2,
                "search_kinds": search_kinds,
                "search_patterns": list(dict.fromkeys(search_pats)),
            },
        }
        evidence = {
            "authn_model": model,
            "scope": "endpoint",
            "subtype": subtype,
            "cwe": list(dict.fromkeys(cwe)),
            "tags": ["authn", epk] + (["payment"] if re.search(r"(?i)pay|refund", endpoint.get("url") or "") else []),
            "sites": decisions[:20],
        }
        return [Finding.make(endpoint, self.vulnclass, state, evidence, [], missing)]
