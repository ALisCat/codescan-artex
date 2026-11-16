#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全局策略抽取：拦截器 / WebMvc 配置 / Spring Security / 租户插件 / 白名单。

只记录策略作用范围与证据行号；是否真正失效仍由 worker 判断。
"""
import re

from .scan import match_pair


def _ant_re(pat):
    s = re.escape(pat)
    s = s.replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    s = re.sub(r"\\\{[^}]+\\\}", "[^/]+", s)
    return re.compile("^" + s + "$")


def match_any(patterns, url):
    if not patterns:
        return False
    for p in patterns:
        try:
            if _ant_re(p).match(url or ""):
                return True
        except Exception:
            continue
    return False


def excluded(excludes, url):
    return match_any(excludes or [], url)


def _line(text, off):
    return text[:off].count("\n") + 1


def _method_body(text, name):
    m = re.search(r"\b" + re.escape(name) + r"\s*\(", text)
    if not m:
        return ""
    o = text.find("(", m.start())
    c = match_pair(text, o, "(", ")")
    if c < 0:
        return ""
    b = text.find("{", c)
    if b < 0:
        return ""
    e = match_pair(text, b, "{", "}")
    return text[b:e + 1] if e > 0 else ""


def _str_args(text):
    return re.findall(r'"([^"]+)"', text)


def _patterns_from(text, names=r"match|antMatchers|requestMatchers|addPathPatterns|startsWith|equals"):
    pats = []
    for m in re.finditer(r"(?:" + names + r")\s*\(([^)]*)\)", text):
        for s in _str_args(m.group(1)):
            if s.startswith("/") or s.startswith("**"):
                pats.append(s)
    return pats


def _whitelist(paths):
    out = []
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.match(r"\s*whitelist\s*:\s*$", line):
                base = len(line) - len(line.lstrip())
                for nxt in lines[i + 1:]:
                    if not nxt.strip():
                        continue
                    ind = len(nxt) - len(nxt.lstrip())
                    if ind <= base:
                        break
                    m = re.match(r"\s*-\s*[\"']?([^\"'\s]+)", nxt)
                    if m and m.group(1).startswith("/"):
                        out.append(m.group(1))
    return out


def extract_policies(ctx):
    """返回 [{kind, rule, patterns, excludes, file, line, source}]。"""
    classes = ctx.graph.get("classes", [])
    files = set()
    for c in classes:
        f = c.get("file")
        cls = (c.get("fqn") or "").split(".")[-1]
        if not f:
            continue
        if re.search(r"(?i)(Interceptor|Filter|Security|WebMvc|WebConfig|Auth|Tenant)", cls):
            files.add(f)

    ymls = []
    try:
        for pat in ("application*.yml", "application*.yaml", "application*.properties"):
            ymls.extend(ctx.root.rglob(pat))
    except Exception:
        pass
    wl = _whitelist(ymls)

    policies = []
    mvc_patterns, mvc_excludes = [], []
    registered = set()

    for file in sorted(files):
        text = ctx.read(file, 1, 100000)
        if not text:
            continue
        cls = file.rsplit("/", 1)[-1].replace(".java", "")

        # WebMvc：拦截器注册范围
        if "WebMvcConfigurer" in text or "addInterceptors" in text:
            for m in re.finditer(r"addPathPatterns\s*\(([^)]*)\)", text):
                mvc_patterns.extend(_str_args(m.group(1)))
            for m in re.finditer(r"excludePathPatterns\s*\(([^)]*)\)", text):
                mvc_excludes.extend(_str_args(m.group(1)))
            for m in re.finditer(r"addInterceptor\s*\(([^)]*)\)", text):
                arg = re.sub(r"\bnew\b", "", m.group(1)).strip()
                for ident in re.findall(r"[A-Za-z_$][\w$]*", arg):
                    registered.add(ident.lower())
            if "excludePathPatterns" in text and wl:
                mvc_excludes.extend(wl)

        # HandlerInterceptor
        if "HandlerInterceptor" in text or "preHandle" in text:
            pre = _method_body(text, "preHandle")
            if pre:
                line = _line(text, text.find("preHandle"))
                has_401 = bool(re.search(r"401|未登录|登录已失效|unauthor", pre, re.I))
                has_principal = bool(re.search(r"UserContext\.set|getHeader\s*\(\s*[\"']token|SecurityContext|Principal", pre))
                if has_401 and has_principal:
                    policies.append({
                        "kind": "authentication", "rule": "token -> principal",
                        "patterns": [], "excludes": [], "file": file, "line": line,
                        "source": "interceptor:%s.preHandle" % cls,
                    })
                role = None
                m = re.search(r'[\"\']([A-Z][A-Z0-9_]+)[\"\']\s*\.equals\s*\([^)]*getRole', pre)
                if not m:
                    m = re.search(r'getRole\s*\([^)]*\)[^;]{0,40}?[\"\']([A-Z][A-Z0-9_]+)[\"\']', pre)
                if m and re.search(r"403|无权|forbidden|Forbidden", pre):
                    role = m.group(1)
                admin_body = _method_body(text, "needAdmin")
                admin_pats = _patterns_from(admin_body) if admin_body else []
                if role:
                    pats = _patterns_from(text) or admin_pats or ["/**"]
                    policies.append({
                        "kind": "role", "rule": role, "patterns": pats,
                        "excludes": [], "file": file, "line": line,
                        "source": "interceptor:%s.preHandle" % cls,
                        "enforced": True,
                    })
                elif admin_pats:
                    # needAdmin 声明了路径，但 preHandle 没有调用/没有角色判断：死守卫
                    policies.append({
                        "kind": "role", "rule": "ADMIN", "patterns": admin_pats,
                        "excludes": [], "file": file,
                        "line": _line(text, text.find("needAdmin")),
                        "source": "interceptor:%s.needAdmin(dead)" % cls,
                        "enforced": False,
                    })

        # Spring Security
        if "SecurityFilterChain" in text or "authorizeHttpRequests" in text:
            for m in re.finditer(r'\.?(?:requestMatchers|antMatchers)\s*\(([^)]*)\)\s*\.(hasRole|hasAnyRole|hasAuthority|authenticated|permitAll)\s*\(([^)]*)\)', text):
                pats = _str_args(m.group(1))
                fn = m.group(2)
                args = m.group(3)
                if fn in ("hasRole", "hasAnyRole", "hasAuthority"):
                    roles = _str_args(args)
                    if not roles and re.match(r"\w+", args.strip()):
                        roles = [args.strip()]
                    policies.append({
                        "kind": "role", "rule": ",".join(roles) or fn,
                        "patterns": pats, "excludes": [], "file": file,
                        "line": _line(text, m.start()), "source": "spring-security",
                    })
                elif fn == "authenticated":
                    policies.append({
                        "kind": "authentication", "rule": "authenticated",
                        "patterns": pats, "excludes": [], "file": file,
                        "line": _line(text, m.start()), "source": "spring-security",
                    })

        # 租户插件
        if "TenantLineHandler" in text or re.search(r"getTenantId\s*\(", text):
            if "TenantLineHandler" in text:
                policies.append({
                    "kind": "tenant", "rule": "global tenant plugin",
                    "patterns": ["/**"], "excludes": [], "file": file,
                    "line": _line(text, text.find("TenantLineHandler")),
                    "source": "tenant-plugin",
                })

    # 显式 WebMvc 注册存在但没提到该拦截器 → 视为未生效
    if registered:
        for p in policies:
            src = p.get("source") or ""
            if src.startswith("interceptor:"):
                cls = src.split(":", 1)[1].split(".")[0]
                if cls.lower() not in registered:
                    p["enforced"] = False

    # 把 WebMvc 范围套到没有显式范围的认证策略上
    for p in policies:
        if p["kind"] == "authentication" and not p["patterns"]:
            p["patterns"] = mvc_patterns or ["/**"]
            p["excludes"] = mvc_excludes or wl
    return policies
