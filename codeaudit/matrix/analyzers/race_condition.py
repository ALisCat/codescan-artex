#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Race condition：库存/锁号/挂号/支付等状态变更是否有锁或幂等。"""
import re

from .base import Analyzer, Finding, POSSIBLE, IMPOSSIBLE
from .patterns import scan, has_input, model, search_policy

CANDIDATE = re.compile(r"(?i)(lock|registercancel|registercheckin|pay|refund|stock|zerolock|cancel|recharge|notifycallback)")
STATE = [
    re.compile(r"(?i)\.(save|update|updateById|insert|delete|remove|increment|decrement)\s*\("),
]
LOCK = [
    re.compile(r"(?i)(RLock|tryLock|synchronized|@Transactional|for\s+update|setIfAbsent|increment\s*\()"),
]


class RaceConditionAnalyzer(Analyzer):
    vulnclass = "race_condition"

    def analyze(self, endpoint, ctx):
        text = "%s %s" % (endpoint.get("url") or "", endpoint.get("handler") or "")
        if not CANDIDATE.search(text) or not has_input(endpoint):
            return [Finding.make(endpoint, self.vulnclass, IMPOSSIBLE, {
                "scope": "endpoint", "subtype": "not-contended-state",
            }, [], "not a contended state endpoint")]
        states = scan(ctx, endpoint, STATE, "state_change")
        if not states:
            return [Finding.make(endpoint, self.vulnclass, IMPOSSIBLE, {
                "scope": "endpoint", "subtype": "no-state-change",
            }, [], "no state change")]
        guards = scan(ctx, endpoint, LOCK, "lock_or_idempotency")
        gaps = [] if guards else ["lock_or_idempotency_missing"]
        m = model(["lock_or_idempotency"], states + guards, gaps, extra={
            "state_changes": states[:15],
            "locks": guards[:10],
            "search_policy": search_policy(gaps, ["RLock|tryLock|synchronized|@Transactional|for update"]),
        })
        ev = {
            "race_model": m, "scope": "endpoint",
            "subtype": "race-condition" if gaps else "lock-present",
            "cwe": ["CWE-362"], "tags": ["race-condition"],
            "sites": states[:15],
        }
        return [Finding.make(endpoint, self.vulnclass, POSSIBLE, ev, [], gaps[0] if gaps else None)]
