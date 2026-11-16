#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从流程方法源码组装 authz_model。

主判据是行为签名：principal + resource/role + 条件 + 拒绝路径。
方法名不参与判定；未解析的调用只作为 unknown/candidate。
"""
import re

from .scan import scan_body, parse_signature
from .policy import extract_policies, match_any, excluded

KIND_CN = {
    "authentication": "认证",
    "role": "角色",
    "tenant": "租户",
    "ownership": "归属",
}

ID_NAME = re.compile(r"(?i)^(id|.*Id|.*_id|.*No|.*no|.*Code|.*code|path|filepath|filename|attachment|archive|record|patient|resource)$")
ADMIN_PATH = re.compile(r"(?i)/(admin|manage|report|system|config|backstage|console)(/|$)")
PUBLIC_PATH = re.compile(r"(?i)/(auth/(login|register)|login|health|error)(/|$)")
ACCESSOR = re.compile(r"^(get|set|is)[A-Z]")
IGNORE_METHODS = {
    "equals", "equalsIgnoreCase", "toString", "hashCode", "compareTo", "valueOf",
    "parseLong", "parseInt", "parseDate", "format", "trim", "isEmpty", "isBlank",
    "isNotEmpty", "contains", "size", "length", "add", "put", "get", "stream",
}

SEARCH_PATTERNS = {
    "ownership": ["owner|patientId|userId|checkOwner|ensureAccess|belong|canAccess"],
    "tenant": ["tenant|tenantId|hospId|orgId|deptId"],
    "role": ["@PreAuthorize|@Secured|@RolesAllowed|@RequiresRoles|@SaCheckRole|hasRole|hasAuthority"],
    "authentication": ["HandlerInterceptor|WebMvcConfigurer|SecurityFilterChain|OncePerRequestFilter|token|401"],
}


def _dedup(items, keys):
    seen, out = set(), []
    for it in items:
        k = tuple(it.get(x) for x in keys)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _ann_inner(text, name):
    m = re.search(r"@" + name + r"\s*\(", text)
    if not m:
        return None, 0
    o = m.end() - 1
    from .scan import match_pair
    c = match_pair(text, o, "(", ")")
    if c < 0:
        return None, 0
    return text[o + 1:c], m.start()


def _annotation_decisions(ctx, endpoint):
    """解析声明式守卫：@PreAuthorize/@Secured/@RolesAllowed/Shiro/Sa-Token。"""
    out = []
    eline = endpoint.get("line") or 1
    base = max(1, eline - 20)
    text = ctx.read(endpoint.get("file"), base, eline + 8)
    # 只保留到本方法签名之前，避免把下一个方法的注解算进来
    lines = text.splitlines()
    cut = len(lines)
    for i, line in enumerate(lines):
        if i >= (eline - base) and re.search(r"\b(public|private|protected)\b", line) and "(" in line:
            cut = i
            break
    text = "\n".join(lines[:cut])

    for name, pep in (
        ("PreAuthorize", "Spring @PreAuthorize"),
        ("Secured", "Spring @Secured"),
        ("RolesAllowed", "JSR-250 @RolesAllowed"),
        ("RequiresRoles", "Shiro @RequiresRoles"),
        ("SaCheckRole", "Sa-Token @SaCheckRole"),
    ):
        inner, off = _ann_inner(text, name)
        if inner is None:
            continue
        roles = re.findall(r"has(?:Any)?Role\s*\(\s*'([^']+)'", inner)
        if not roles:
            roles = re.findall(r"hasAuthority\s*\(\s*'([^']+)'", inner)
        if not roles:
            roles = re.findall(r"'([^']+)'", inner) or re.findall(r'\"([^\"]+)\"', inner)
        val = ",".join(dict.fromkeys(roles)) if roles else inner.strip()
        out.append({
            "kind": "role", "rule": val, "condition": ("@" + name + "(" + inner + ")")[:200],
            "source": "annotation", "pep": pep,
            "file": endpoint.get("file"), "line": base + text[:off].count("\n"),
        })
    # 未知语义的自定义注解：只标记 candidate，不当作有效决策
    for m in re.finditer(r"@(\w*(?:Check|Permission|Role|Auth)\w*)", text):
        name = m.group(1)
        if name in ("PreAuthorize", "Secured", "RolesAllowed", "RequiresRoles", "SaCheckRole"):
            continue
        line = base + text[:m.start()].count("\n")
        out.append({
            "kind": "role", "rule": name, "condition": "@" + name,
            "source": "annotation-candidate", "pep": "custom",
            "file": endpoint.get("file"), "line": line,
        })
    return _dedup(out, ("kind", "rule", "file", "line"))

def _policy_decisions(ctx, endpoint):
    pols = getattr(ctx, "_authz_policies", None)
    if pols is None:
        pols = extract_policies(ctx)
        ctx._authz_policies = pols
    url = endpoint.get("url") or ""
    out, needed, dead = [], [], []
    for p in pols:
        if not match_any(p.get("patterns"), url) or excluded(p.get("excludes"), url):
            continue
        if p.get("kind") == "role":
            needed.append("role")
        if not p.get("enforced", True):
            dead.append("策略未生效（未注册/未被 preHandle 调用）: %s @ %s:%s" % (
                p.get("source"), p.get("file"), p.get("line")))
            continue
        out.append({
            "kind": p.get("kind"), "rule": p.get("rule"),
            "source": "policy", "pep": p.get("source"),
            "condition": "patterns: %s" % ", ".join(p.get("patterns") or []),
            "file": p.get("file"), "line": p.get("line"), "resolved": True,
        })
    return out, needed, dead


def _unresolved_helpers(ctx, endpoint, principals, resources):
    """未解析调用：参数里同时出现 principal 和资源标识时，标记 candidate。"""
    pnames = {p.get("var") for p in principals if p.get("var")}
    rnames = {r.get("var") for r in resources if r.get("var")}
    for p in endpoint.get("params", []):
        n = p.get("name") or ""
        if p.get("type") in ("Long", "Integer", "String") and ID_NAME.match(n):
            rnames.add(n)
    out = []
    for u in endpoint.get("unresolved", []):
        name = u.get("name") or ""
        if ACCESSOR.match(name) or name in IGNORE_METHODS:
            continue
        text = ctx.read(u.get("file"), u.get("line"), u.get("line"))
        has_p = any(re.search(r"\b" + re.escape(n) + r"\b", text) for n in pnames)
        has_r = any(re.search(r"\b" + re.escape(n) + r"\b", text) for n in rnames)
        if has_p and has_r:
            out.append({
                "method": name, "call_file": u.get("file"), "call_line": u.get("line"),
                "scope": u.get("scope") or u.get("scopeText"),
                "candidates": u.get("candidates") or [],
                "resolved": False,
                "reason": "参数同时包含 principal 和资源标识",
            })
    return _dedup(out, ("method", "call_file", "call_line"))


def build_authz_model(endpoint, ctx, resources, guards_seen=None):
    """返回 (authz_model, guard_helpers)。"""
    principals, res_facts, guard_facts = [], [], []
    unresolved_calls = []
    for step in endpoint.get("flow", []):
        if step.get("kind") != "method":
            continue
        body = ctx.method_body(step)
        if not body:
            continue
        params = parse_signature(body)
        if not params:
            m = ctx.methods.get(step.get("method_id")) or {}
            params = [{"type": t, "name": ""} for t in (m.get("params") or [])]
        facts = scan_body(body, step.get("line") or 1, params)
        for p in facts["principals"]:
            p.update({"file": step.get("file"), "method": step.get("name")})
            principals.append(p)
        for r in facts["resources"]:
            r.update({"file": step.get("file"), "method": step.get("name")})
            if r.get("source") != "param":
                res_facts.insert(0, r)
            else:
                res_facts.append(r)
        for g in facts["guards"]:
            g.update({"file": step.get("file"), "method": step.get("name"),
                      "target_file": step.get("file"), "target_line": g.get("line"),
                      "target_end": step.get("end"), "resolved": True})
            guard_facts.append(g)

        # 条件里的 helper 调用：解析到实现后，用返回值/方法体判断
        for gc in facts.get("guard_calls", []):
            if ACCESSOR.match(gc["name"]) or gc["name"] in IGNORE_METHODS:
                continue
            target = None
            for c in ctx.calls_in(step):
                if c.get("name") == gc["name"] and abs((c.get("line") or 0) - gc["line"]) <= 3:
                    target = c
                    break
            callee = (target or {}).get("callee")
            m = ctx.methods.get(callee) if callee else None
            if not m:
                unresolved_calls.append({
                    "method": gc["name"], "call_file": step.get("file"),
                    "call_line": gc["line"], "resolved": False,
                    "reason": "条件中调用，参数含 principal + 资源，但实现未解析",
                    "condition": gc.get("condition"),
                })
                continue
            hb = ctx.read(m.get("file"), m.get("line"), m.get("end"))
            hparams = parse_signature(hb)
            hf = scan_body(hb, m.get("line") or 1, hparams, require_deny=False)
            for g in hf["guards"]:
                g.update({"file": m.get("file"), "method": m.get("name"),
                          "source": "return-check" if g.get("source") == "return-expr" else g.get("source"),
                          "target_file": m.get("file"), "target_line": g.get("line"),
                          "target_end": m.get("end"), "resolved": True,
                          "call_file": step.get("file"), "call_line": gc.get("line")})
                guard_facts.append(g)

    principals = _dedup(principals, ("var", "file", "line"))
    guard_facts = _dedup(guard_facts, ("kind", "rule", "file", "line"))

    decisions = []
    if principals:
        p = principals[0]
        decisions.append({
            "kind": "authentication",
            "rule": "principal: %s (%s)" % (p.get("var"), p.get("source")),
            "source": "principal", "file": p.get("file"), "line": p.get("line"),
            "method": p.get("method"), "resolved": True,
        })
    decisions.extend(guard_facts)
    policy_dec, policy_required, policy_dead = _policy_decisions(ctx, endpoint)
    decisions.extend(policy_dec)
    ann_dec = _annotation_decisions(ctx, endpoint)
    decisions.extend(ann_dec)
    for d in ann_dec:
        if d.get("kind") == "role" and d.get("source") == "annotation":
            decisions.append({
                "kind": "authentication", "rule": "implied by role annotation",
                "source": "annotation-implied", "pep": d.get("pep"),
                "file": d.get("file"), "line": d.get("line"), "resolved": True,
            })
            break
    decisions = _dedup(decisions, ("kind", "rule", "file", "line"))

    # resource：优先用扫描到的 DAO/DTO 变量，其次用 endpoint 的资源访问/参数
    resource = None
    if res_facts:
        r = res_facts[0]
        resource = {
            "var": r.get("var"), "type": r.get("type"),
            "identifier": r.get("var"), "source": r.get("source"),
            "file": r.get("file"), "line": r.get("line"),
        }
    elif resources:
        r = resources[0]
        resource = {
            "var": None, "type": r.get("dao") or r.get("kind"),
            "identifier": r.get("method") or r.get("api"),
            "source": r.get("kind"), "file": r.get("file"), "line": r.get("line"),
        }

    params = [p for p in endpoint.get("params", [])
              if p.get("name") and not str(p.get("name")).startswith('"')]
    id_params = [p.get("name") for p in params if ID_NAME.match(p.get("name") or "")]
    tenant_params = [p.get("name") for p in params
                     if re.search(r"(?i)tenant|hosp|org|dept", p.get("name") or "")]

    required = []
    if not PUBLIC_PATH.search(endpoint.get("url") or ""):
        if resource or id_params or resources:
            required.append("authentication")
    if id_params and resource:
        required.append("ownership")
    if tenant_params:
        required.append("tenant")
    if "role" in policy_required or ADMIN_PATH.search(endpoint.get("url") or ""):
        required.append("role")

    # 注解 candidate 不抵 required
    effective = [d for d in decisions if d.get("source") != "annotation-candidate"]
    observed = []
    for d in effective:
        k = d.get("kind")
        if k and k not in observed:
            observed.append(k)
    gaps = [k for k in required if k not in observed]

    unknowns = list(policy_dead)
    has_authentication = "authentication" in observed
    if not principals and (resource or resources) and not has_authentication:
        unknowns.append("未发现 principal 来源（可能是全局拦截器，需确认）")
    unresolved = _unresolved_helpers(ctx, endpoint, principals, res_facts)
    for u in unresolved + unresolved_calls:
        unknowns.append("未解析的守卫候选: %s @ %s:%s" % (
            u.get("method"), u.get("call_file"), u.get("call_line")))

    # 全局搜索预算：只为 required 中未命中的类型开放；命中后不再扩大搜索。
    search_kinds = list(gaps)
    if not search_kinds and any(u.startswith("未解析") for u in unknowns):
        search_kinds = list(required)
    search_patterns = []
    for k in search_kinds:
        search_patterns.extend(SEARCH_PATTERNS.get(k, []))
    search_policy = {
        "allow_global_search": bool(search_kinds),
        "search_budget": 2,
        "search_kinds": search_kinds,
        "search_patterns": list(dict.fromkeys(search_patterns)),
    }

    model = {
        "principal": principals[0] if principals else None,
        "resource": resource,
        "decisions": decisions,
        "required": required,
        "coverage": [k for k in required if k in observed],
        "gaps": gaps,
        "unknowns": unknowns,
        "search_policy": search_policy,
    }

    # guard_helpers：只给需要另读的实现；同文件 inline 已经有行号
    helpers = []
    for g in guard_facts:
        if g.get("file") and g.get("line"):
            helpers.append({
                "kind": g.get("kind"), "rule": g.get("rule"),
                "method": g.get("method"), "resolved": True,
                "call_file": g.get("file"), "call_line": g.get("line"),
                "target_file": g.get("target_file"), "target_line": g.get("target_line"),
                "target_end": g.get("target_end"),
                "condition": g.get("condition"),
            })
    helpers.extend(unresolved)
    helpers.extend(unresolved_calls)
    helpers = _dedup(helpers, ("method", "call_file", "call_line"))
    return model, helpers[:12]
