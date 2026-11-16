#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""business-logic：支付/退款/订单状态/金额/幂等。

只做结构提示：请求体是否携带金额/状态/租户/订单标识，是否存在状态写回；
是否真正可篡改由 worker 判断。
"""
import re

from .base import Analyzer, Finding, POSSIBLE, IMPOSSIBLE
from .patterns import scan, names, has_input, model, search_policy

STATE = [re.compile(r"(?i)\.(save|saveOrUpdate|update|updateById|insert|delete|remove|cancel|refund|pay|send)\s*\(")]
AMOUNT = re.compile(r"(?i)amount|fee|price|money|total|refund")
STATUS = re.compile(r"(?i)status|state|paid|payStatus|orderStatus")
ORDER = re.compile(r"(?i)orderNo|orderId|regId|registeredId|regMark|billNo")
TENANT = re.compile(r"(?i)tenant|branch|hosp|org|dept")
CANDIDATE = re.compile(r"(?i)(pay|refund|order|registercancel|registercheckin(?!list)|recharge|lock|notifycallback|zerolock)")


class BusinessLogicAnalyzer(Analyzer):
    vulnclass = "business_logic"

    def analyze(self, endpoint, ctx):
        text = "%s %s" % (endpoint.get("url") or "", endpoint.get("handler") or "")
        if not CANDIDATE.search(text):
            return [Finding.make(endpoint, self.vulnclass, IMPOSSIBLE, {
                "scope": "endpoint", "subtype": "not-business-logic",
            }, [], "not a payment/order/state endpoint")]

        ns = names(endpoint)
        fields = []
        if any(AMOUNT.search(n) for n in ns):
            fields.append("amount")
        if any(STATUS.search(n) for n in ns):
            fields.append("status")
        if any(ORDER.search(n) for n in ns):
            fields.append("order_identifier")
        if any(TENANT.search(n) for n in ns):
            fields.append("tenant")
        state_sites = scan(ctx, endpoint, STATE, "state_change")
        if not state_sites and not fields:
            return [Finding.make(endpoint, self.vulnclass, IMPOSSIBLE, {
                "scope": "endpoint", "subtype": "not-business-logic",
            }, [], "no state change or business field")]

        required = []
        gaps = []
        if "amount" in fields:
            required.append("amount_recomputed_server_side")
            gaps.append("amount_from_request")
        if "status" in fields:
            required.append("status_server_controlled")
            gaps.append("status_from_request")
        if "order_identifier" in fields:
            required.append("order_bound_to_principal")
            gaps.append("order_not_bound_to_principal")
        if "tenant" in fields:
            required.append("tenant_bound_to_principal")
            gaps.append("tenant_from_request")
        if state_sites:
            required.append("idempotency_or_state_guard")
            if not fields:
                required.append("server_side_state_invariants")
                gaps.append("state_invariants_unverified")

        decisions = state_sites[:20]
        subtype = "payment-or-order-state"
        if gaps:
            subtype = gaps[0]
        bm = model(required, decisions, gaps, extra={
            "client_fields": fields,
            "state_changes": state_sites[:20],
            "search_policy": search_policy(gaps, [
                "recompute|calculate|amount|fee|price",
                "status|orderStatus|paid|refund",
                "Objects\\.equals|equals|RLock|tryLock|@Transactional|for update",
            ]),
        })
        ev = {
            "business_logic_model": bm,
            "scope": "endpoint",
            "subtype": subtype,
            "cwe": ["CWE-840", "CWE-862"],
            "tags": ["business-logic"] + (["payment"] if re.search(r"(?i)pay|refund", text) else []),
            "sites": state_sites[:20],
        }
        missing = "business invariant: " + ", ".join(gaps) if gaps else None
        return [Finding.make(endpoint, self.vulnclass, POSSIBLE, ev, [], missing)]
