#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""源码级守卫扫描：不依赖方法名，按 principal/resource/条件/拒绝路径识别。"""
import re

PRINCIPAL_TYPES = {"LoginUser", "RequestHeader", "Principal", "UserDetails", "Authentication"}
PRINCIPAL_SRC = re.compile(r"UserContext|RequestHeaderUtil|getRequestHeader|SecurityContext|@AuthenticationPrincipal|LoginUser|RequestHeader")
RESOURCE_SRC = re.compile(r"Mapper\.|Repository\.|Dao\.|Mapper\s*\.|findById|getById|selectOne|selectList|selectPage|getOne|page\s*\(")
ID_PARAM = re.compile(r"(?i)(id|no|code|key|archive|patient|order|reg|card|owner|user|tenant|hosp)")
DENY = re.compile(r"throw\s+new|sendError\s*\(\s*(401|403)|sendRedirect|return\s+.*(?:error|Error|fail|Fail|403|401)")


def match_pair(s, o, op, cl):
    d = 0
    for i in range(o, len(s)):
        if s[i] == op:
            d += 1
        elif s[i] == cl:
            d -= 1
            if d == 0:
                return i
    return -1


def split_args(s):
    out, d, b = [], 0, ""
    for ch in s:
        if ch in "(<[":
            d += 1
        elif ch in ")>]":
            d -= 1
        if ch == "," and d == 0:
            out.append(b.strip()); b = ""
        else:
            b += ch
    if b.strip():
        out.append(b.strip())
    return out


def find_blocks(body):
    """返回 [(line, cond, then_text, else_text)]，支持 if (...) { } else { }。"""
    out = []
    for m in re.finditer(r"\bif\s*\(", body):
        o = body.find("(", m.start())
        close = match_pair(body, o, "(", ")")
        if close < 0:
            continue
        cond = body[o + 1:close]
        j = close + 1
        while j < len(body) and body[j] in " \t\r\n":
            j += 1
        if j < len(body) and body[j] == "{":
            e = match_pair(body, j, "{", "}")
            then = body[j + 1:e] if e > 0 else ""
            k = e + 1 if e > 0 else close + 1
        else:
            k = body.find(";", j)
            then = body[j:k + 1] if k > 0 else ""
            k = k + 1 if k > 0 else close + 1
        else_txt = ""
        rest = body[k:]
        mm = re.match(r"\s*else\s*\{", rest)
        if mm:
            b0 = k + mm.end() - 1
            e2 = match_pair(body, b0, "{", "}")
            else_txt = body[b0 + 1:e2] if e2 > 0 else ""
        out.append((body[:m.start()].count("\n") + 1, cond, then, else_txt))
    return out


def _kind_from_field(expr):
    e = expr.lower()
    if re.search(r"tenant|hosp|org|dept|branch", e):
        return "tenant"
    if re.search(r"role|admin|permission|auth", e):
        return "role"
    if re.search(r"owner|patient|user|id|no|code", e):
        return "ownership"
    return ""


def _is_principal(expr, pvars):
    return any(re.search(r"\b" + re.escape(v) + r"\b", expr) for v in pvars)


def _is_resource(expr, rvars):
    return any(re.search(r"\b" + re.escape(v) + r"\b", expr) for v in rvars)


def _const_role(expr):
    return bool(re.search(r'"[A-Z][A-Z0-9_]{2,}"', expr))


def _eval_pair(a, b, pvars, rvars, out):
    if _is_principal(a, pvars) and _is_resource(b, rvars):
        out.append((_kind_from_field(b), "%s == %s" % (b, a)))
    elif _is_principal(b, pvars) and _is_resource(a, rvars):
        out.append((_kind_from_field(a), "%s == %s" % (a, b)))
    elif _is_principal(a, pvars) and _const_role(b):
        out.append(("role", "%s == %s" % (a, b)))
    elif _is_principal(b, pvars) and _const_role(a):
        out.append(("role", "%s == %s" % (a, b)))


def parse_comparison(cond, pvars, rvars):
    """返回 [(kind, rule)]；不依赖方法名。"""
    out = []
    c = cond.strip()
    # Objects.equals(a, b)
    for m in re.finditer(r"Objects\.equals\s*\(", c):
        o = m.end() - 1
        close = match_pair(c, o, "(", ")")
        if close < 0:
            continue
        args = split_args(c[o + 1:close])
        if len(args) == 2:
            _eval_pair(args[0].strip(), args[1].strip(), pvars, rvars, out)
    # a.equals(b)，排除 Objects.equals
    for m in re.finditer(r"(?<!Objects)(?<![\w.])([\w.()\[\]\"']+)\.equals(?:IgnoreCase)?\s*\(", c):
        o = m.end() - 1
        close = match_pair(c, o, "(", ")")
        if close < 0:
            continue
        args = split_args(c[o + 1:close])
        if len(args) != 1:
            continue
        _eval_pair(m.group(1).strip(), args[0].strip(), pvars, rvars, out)
    # a == b / a != b
    for m in re.finditer(r"([\w.()\[\]\"]+)\s*(?:==|!=)\s*([\w.()\[\]\"]+)", c):
        _eval_pair(m.group(1).strip(), m.group(2).strip(), pvars, rvars, out)
    # hasRole("ADMIN") / hasAnyRole(...)
    for m in re.finditer(r"has(?:Any)?Role\s*\(\s*[\"']([^\"']+)[\"']", c):
        out.append(("role", "role in %s" % m.group(1)))
    # 去重
    seen, uniq = set(), []
    for k, r in out:
        if not k:
            continue
        key = (k, r)
        if key in seen:
            continue
        seen.add(key); uniq.append((k, r))
    return uniq

def scan_body(body, base_line, params=None, require_deny=True):
    """返回 {principals, resources, guards, guard_calls}。"""
    params = params or []
    pvars, rvars = set(), set()
    p_facts, r_facts = [], []

    for p in params:
        name, typ = p.get("name"), p.get("type", "")
        if typ.split("<")[0] in PRINCIPAL_TYPES or re.search(r"(?i)LoginUser|RequestHeader", typ):
            pvars.add(name); p_facts.append({"var": name, "type": typ, "source": "param", "line": base_line})
        elif ID_PARAM.search(name or ""):
            rvars.add(name); r_facts.append({"var": name, "type": typ, "source": "param", "line": base_line})

    for m in re.finditer(r"\b(?:final\s+)?([A-Z][\w.<>\[\]]*)\s+(\w+)\s*=\s*([^;]+);", body):
        typ, var, rhs = m.group(1), m.group(2), m.group(3)
        line = base_line + body[:m.start()].count("\n")
        if PRINCIPAL_SRC.search(rhs) or typ.split("<")[0] in PRINCIPAL_TYPES:
            pvars.add(var); p_facts.append({"var": var, "type": typ, "source": rhs.strip()[:120], "line": line})
        elif RESOURCE_SRC.search(rhs) or re.search(r"(?i)(DTO|Entity|Detail|Archive|Order|Appointment|Patient|Notice)$", typ):
            rvars.add(var); r_facts.append({"var": var, "type": typ, "source": rhs.strip()[:120], "line": line})

    guards = []
    guard_calls = []
    for off, cond, then, els in find_blocks(body):
        line = base_line + off - 1
        deny = bool(DENY.search(then)) or bool(DENY.search(els))
        if require_deny and not deny:
            continue
        if not then and not els:
            continue
        for kind, rule in parse_comparison(cond, pvars, rvars):
            guards.append({"kind": kind, "rule": rule, "condition": cond.strip()[:240],
                           "line": line, "deny": deny, "source": "inline"})
        # 条件里调用 helper：参数含 principal + resource → 返回值/内部守卫候选
        for m in re.finditer(r"(?:([\w.]+)\.)?(\w+)\s*\(", cond):
            o = m.end() - 1
            c = match_pair(cond, o, "(", ")")
            if c < 0:
                continue
            args = split_args(cond[o + 1:c])
            has_p = any(_is_principal(a, pvars) for a in args)
            has_r = any(_is_resource(a, rvars) for a in args)
            if has_p and has_r:
                guard_calls.append({
                    "name": m.group(2), "receiver": m.group(1) or "",
                    "args": args, "condition": cond.strip()[:240], "line": line,
                })

    # 返回值本身是布尔表达式：order.ownerId == user.id
    if not require_deny:
        for m in re.finditer(r"\breturn\s+([^;]+);", body):
            expr = m.group(1).strip()
            line = base_line + body[:m.start()].count("\n")
            for kind, rule in parse_comparison(expr, pvars, rvars):
                guards.append({"kind": kind, "rule": rule, "condition": expr[:240],
                               "line": line, "deny": False, "source": "return-expr"})

    # 去重
    seen, uniq = set(), []
    for g in guards:
        key = (g["kind"], g["rule"], g["line"])
        if key in seen:
            continue
        seen.add(key); uniq.append(g)
    return {"principals": p_facts, "resources": r_facts, "guards": uniq,
            "guard_calls": guard_calls}


def parse_signature(body):
    """从方法源码头部解析参数名和类型，弥补 graph 只存类型的问题。"""
    m = re.search(r"\)\s*(?:throws\s+[\w.,\s<>]+)?\{", body)
    head = body[:m.start() + 1] if m else body.split("{", 1)[0]
    c = head.rfind(")")
    if c < 0:
        return []
    depth, o = 0, -1
    for i in range(c, -1, -1):
        if head[i] == ")":
            depth += 1
        elif head[i] == "(":
            depth -= 1
            if depth == 0:
                o = i
                break
    if o < 0:
        return []
    out = []
    for a in split_args(head[o + 1:c]):
        a = re.sub(r"@[\w.]+(\([^)]*\))?\s*", "", a).strip()
        a = re.sub(r"\bfinal\s+", "", a)
        m = re.match(r"(?s)(.+?)\s+(\w+)$", a)
        if m:
            out.append({"type": m.group(1).strip(), "name": m.group(2)})
        elif a:
            out.append({"type": a, "name": ""})
    return out
