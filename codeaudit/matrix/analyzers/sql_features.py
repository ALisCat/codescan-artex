#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQL feature extraction.

The analyzer does not decide whether SQL injection is exploitable. It only
answers whether a SQL-injection *feature* is present:

  raw SQL interpolation / concatenation / dynamic SQL structure

A bound parameter (#{} / ? / eq) is a neutralizer of the value slot, not a
"safe" conclusion. Guards (sort whitelist, etc.) do not remove a feature.
"""
import re

RAW_SQL = "${"
PARAM_SQL = re.compile(r"#\{|\?")

WRAPPER_RAW = {
    "last", "apply", "inSql", "orderBy", "orderByAsc", "orderByDesc", "having",
}
WRAPPER_PARAM = {"eq", "ne", "like", "in", "ge", "le", "gt", "lt"}

JDBC_CALL = re.compile(
    r"\b(executeQuery|executeUpdate|executeBatch|execute|prepareStatement|createStatement)\s*\("
)
JDBC_TEMPLATE = re.compile(
    r"\b(?:jdbcTemplate|namedParameterJdbcTemplate|NamedParameterJdbcTemplate)\s*\.\s*(\w+)\s*\("
)
SQL_FORMAT = re.compile(r"(?:String\.format|MessageFormat\.format|StringBuilder|StringBuffer|String\.join)\s*\(")


def _strip_parens(expr):
    expr = (expr or "").strip()
    while expr.startswith("(") and expr.endswith(")"):
        depth = 0
        ok = True
        for i, ch in enumerate(expr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i != len(expr) - 1:
                    ok = False
                    break
        if not ok:
            break
        expr = expr[1:-1].strip()
    return expr


def split_args(text):
    """Split a Java argument list at top-level commas."""
    out, buf, depth = [], "", 0
    quote = ""
    esc = False
    for ch in text or "":
        if quote:
            buf += ch
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
            buf += ch
        elif ch in "(<[":
            depth += 1
            buf += ch
        elif ch in ")>]":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            out.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        out.append(buf.strip())
    return out


def _match_pair(text, start, op="(", cl=")"):
    depth = 0
    quote = ""
    esc = False
    for i in range(start, len(text or "")):
        ch = text[i]
        if quote:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch == op:
            depth += 1
        elif ch == cl:
            depth -= 1
            if depth == 0:
                return i
    return -1


def call_args(text, method):
    """All top-level argument lists for .method(...) in a source expression."""
    out = []
    rx = re.compile(r"\.\s*" + re.escape(method) + r"\s*\(")
    for m in rx.finditer(text or ""):
        op = text.find("(", m.start())
        cl = _match_pair(text, op)
        if cl > op:
            out.append((split_args(text[op + 1:cl]), m.start()))
    return out


def _is_quoted(expr):
    expr = (expr or "").strip()
    if len(expr) < 2 or expr[0] not in "\"'":
        return False
    if expr[-1] != expr[0]:
        return False
    # A concatenation can also start and end with the same quote character.
    # Only treat it as one literal if there is no other unescaped quote inside.
    if expr[0] == '"':
        return re.fullmatch(r'"(?:[^"\\]|\\.)*"', expr) is not None
    return re.fullmatch(r"'(?:[^'\\]|\\.)*'", expr) is not None


def _literal_text(expr):
    """Return (is_literal, text) for a literal or all-literal concat."""
    expr = _strip_parens(expr)
    if _is_quoted(expr):
        return True, expr[1:-1]
    if re.fullmatch(r"-?\d+(?:\.\d+)?[lLfFdD]?", expr) or expr in ("true", "false", "null"):
        return True, expr
    parts = split_top(expr, "+")
    if len(parts) > 1:
        vals, all_lit = [], True
        for p in parts:
            ok, val = _literal_text(p)
            if not ok:
                all_lit = False
                break
            vals.append(val)
        if all_lit:
            return True, "".join(vals)
    return False, ""


def split_top(text, sep):
    out, buf, depth = [], "", 0
    quote = ""
    esc = False
    for ch in text or "":
        if quote:
            buf += ch
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
            buf += ch
        elif ch in "(<[":
            depth += 1
            buf += ch
        elif ch in ")>]":
            depth -= 1
            buf += ch
        elif ch == sep and depth == 0:
            out.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        out.append(buf.strip())
    return out


def literal_mode(text):
    """Classify a literal SQL string: raw / parameterized / fixed."""
    if RAW_SQL in (text or ""):
        return "raw"
    if PARAM_SQL.search(text or ""):
        return "parameterized"
    return "fixed"


def _find_assignment(expr, body):
    name = (expr or "").strip()
    if not re.fullmatch(r"[A-Za-z_$][\w$]*", name):
        return ""
    # Prefer an assignment earlier in the method body. This is deliberately
    # local and heuristic; unknown variables stay unknown.
    matches = list(re.finditer(r"\b" + re.escape(name) + r"\s*=\s*([^;]+);", body or ""))
    if not matches:
        return ""
    return matches[-1].group(1).strip()


def expr_mode(expr, body="", _depth=0):
    """Classify an expression for SQL feature detection.

    Returns:
      raw            dynamic raw SQL construction
      parameterized  literal SQL with only placeholders
      fixed          literal SQL / literal expression
      dynamic        concatenation/format with non-literal parts
      unknown        cannot determine from the local source
    """
    expr = _strip_parens(expr)
    if not expr:
        return "unknown"
    if RAW_SQL in expr:
        return "raw"
    ok, text = _literal_text(expr)
    if ok:
        return literal_mode(text)
    if SQL_FORMAT.search(expr):
        # String.format with a literal format and literal args is not dynamic.
        m = re.search(r"\(([\s\S]*)\)", expr)
        if m:
            args = split_args(m.group(1))
            if args:
                ok0, fmt = _literal_text(args[0])
                if ok0 and all(_literal_text(a)[0] for a in args[1:]):
                    return literal_mode(fmt)
        return "dynamic"
    if "+" in expr and any(not _literal_text(p)[0] for p in split_top(expr, "+")):
        return "dynamic"
    if re.fullmatch(r"[A-Za-z_$][\w$]*", expr):
        if _depth < 4:
            assigned = _find_assignment(expr, body)
            if assigned:
                return expr_mode(assigned, body, _depth + 1)
        return "unknown"
    # A method call may return a constant or a dynamic SQL string; do not
    # pretend it is safe.
    return "unknown"


def _feature(kind, source, file, line, detail, snippet="", **extra):
    out = {
        "kind": kind,
        "source": source,
        "file": file,
        "line": line,
        "detail": detail,
    }
    if snippet:
        out["snippet"] = snippet[:500]
    out.update(extra)
    return out


def sql_text_features(sql, source, file, line, sql_file=None, sql_line=None):
    """Features from MyBatis XML / annotation SQL text."""
    mode = literal_mode(sql or "")
    if mode == "raw":
        return [_feature("raw_interpolation", source, sql_file or file, sql_line or line,
                         "SQL contains ${...}", sql, sql_mode="raw")]
    if mode == "parameterized":
        return []
    return []


def wrapper_features(wrappers, ctx=None):
    """Features / unknowns / neutralizers from MyBatis-Plus wrapper entries."""
    features, unknowns, neutralizers = [], [], []
    seen = set()
    for w in wrappers or []:
        name = w.get("name") or ""
        scope = w.get("scope") or ""
        file, line = w.get("file"), w.get("line")
        # The graph sometimes stores only the receiver (`wrapper`) in scope.
        # Read the call line as a fallback so `.last(condition)` etc. keep args.
        if ctx is not None and file and line and not call_args(scope, name):
            line_text = ctx.read(file, line, line)
            if call_args(line_text, name):
                scope = line_text
        if name not in WRAPPER_RAW:
            if name in WRAPPER_PARAM:
                neutralizers.append({"kind": "bound_parameter", "method": name,
                                     "file": file, "line": line})
            continue
        calls = call_args(scope, name)
        if not calls:
            key = (name, file, line)
            if key not in seen:
                seen.add(key)
                unknowns.append({"reason": "wrapper args unavailable",
                                 "method": name, "file": file, "line": line})
            continue
        for args, _ in calls:
            key = (name, file, line, tuple(args))
            if key in seen:
                continue
            seen.add(key)
            detail = "%s(%s)" % (name, ", ".join(args)[:160])
            if name == "apply" and args:
                # MyBatis-Plus apply("id = {0}", id) is a bound placeholder.
                ok, fmt = _literal_text(args[0])
                if ok and re.search(r"\{\d+\}", fmt) and "${" not in fmt:
                    neutralizers.append({"kind": "bound_parameter", "method": name,
                                         "file": file, "line": line})
                    continue
            modes = [expr_mode(a) for a in args]
            # A variable or method call in a raw wrapper position is already a
            # raw SQL-fragment feature; its source/guards are for the worker.
            if any(m in ("raw", "dynamic", "unknown") for m in modes):
                features.append(_feature("raw_wrapper", "wrapper", file, line,
                                         detail, sql_mode="raw"))
            # all literal → no feature
    return features, unknowns, neutralizers


def jdbc_features(step, ctx):
    """Features from direct JDBC / JdbcTemplate calls in a flow method."""
    body = ctx.method_body(step)
    if not body:
        return [], [], []
    file = step.get("file")
    base = step.get("line") or 1
    features, unknowns, neutralizers = [], [], []
    seen = set()

    def add_call(name, args, pos, sql_arg=True):
        start = base + body[:pos].count("\n")
        snippet = body[pos:pos + 240]
        if not args or not sql_arg:
            return
        mode = expr_mode(args[0], body)
        key = (name, file, start, mode, args[0][:100])
        if key in seen:
            return
        seen.add(key)
        detail = "%s(%s)" % (name, args[0][:160])
        if mode in ("raw", "dynamic"):
            features.append(_feature("dynamic_sql", "jdbc", file, start,
                                     detail, snippet, sql_mode="raw"))
        elif mode in ("parameterized", "fixed"):
            neutralizers.append({"kind": "bound_parameter" if mode == "parameterized" else "fixed_sql",
                                 "method": name, "file": file, "line": start})
        else:
            unknowns.append({"reason": "JDBC SQL expression unresolved", "method": name,
                             "file": file, "line": start, "detail": detail})

    for m in JDBC_CALL.finditer(body):
        name = m.group(1)
        op = body.find("(", m.start())
        cl = _match_pair(body, op)
        if cl <= op:
            continue
        args = split_args(body[op + 1:cl])
        # execute()/executeQuery() with no SQL arg uses a prepared statement;
        # createStatement() itself does not carry SQL.
        if name == "createStatement":
            continue
        add_call(name, args, m.start(), sql_arg=(name not in ("execute", "executeBatch") or bool(args)))
    for m in JDBC_TEMPLATE.finditer(body):
        name = m.group(1)
        op = body.find("(", m.start())
        cl = _match_pair(body, op)
        if cl <= op:
            continue
        args = split_args(body[op + 1:cl])
        add_call("jdbcTemplate." + name, args, m.start())
    return features, unknowns, neutralizers


def collect(endpoint, ctx, jdbc_pats):
    """Collect SQL sites, features, unknowns and neutralizers for one endpoint."""
    sites, features, unknowns, neutralizers = [], [], [], []
    seen = set()

    for d in endpoint.get("daos", []):
        site = d.get("sql_site") or {}
        sql = site.get("sql") or ""
        wrappers = d.get("wrapper") or []
        raw_signals, param_signals = [], []
        for w in wrappers:
            if w.get("name") in WRAPPER_RAW:
                raw_signals.append(w.get("name"))
            elif w.get("name") in WRAPPER_PARAM:
                param_signals.append(w.get("name"))
        if RAW_SQL in sql:
            raw_signals.append("${}")
        if PARAM_SQL.search(sql):
            param_signals.append("#{}")
        key = ("dao", d.get("call_file"), d.get("call_line"), d.get("method"))
        if key not in seen:
            seen.add(key)
            sites.append({
                "kind": d.get("sql_kind") or "unknown",
                "dao": d.get("dao"), "method": d.get("method"),
                "file": d.get("call_file"), "line": d.get("call_line"),
                "sql": sql[:800],
                "sql_file": site.get("file"), "sql_line": site.get("line"),
                "raw_signals": sorted(set(raw_signals)),
                "parameterized_signals": sorted(set(param_signals)),
                "wrapper": [{k: w.get(k) for k in ("name", "file", "line", "scope")}
                            for w in wrappers[:8]],
            })
        if sql:
            features.extend(sql_text_features(sql, d.get("sql_kind") or "sql",
                                              d.get("call_file"), d.get("call_line"),
                                              site.get("file"), site.get("line")))
            mode = literal_mode(sql)
            if mode == "parameterized":
                neutralizers.append({"kind": "bound_parameter", "source": "sql_text",
                                     "file": site.get("file") or d.get("call_file"),
                                     "line": site.get("line") or d.get("call_line")})
        elif wrappers:
            f, u, n = wrapper_features(wrappers, ctx)
            features.extend(f); unknowns.extend(u); neutralizers.extend(n)
        else:
            unknowns.append({"reason": "DAO SQL text unavailable",
                             "dao": d.get("dao"), "method": d.get("method"),
                             "file": d.get("call_file"), "line": d.get("call_line")})

    for step in endpoint.get("flow", []):
        if step.get("kind") != "method":
            continue
        for pat in jdbc_pats:
            for file, line, text in ctx.find(step, pat):
                key = ("jdbc", file, line, text[:40])
                if key in seen:
                    continue
                seen.add(key)
                snippet = ctx.read(file, max(1, line - 1), line + 5)
                sites.append({
                    "kind": "jdbc", "api": text[:80], "file": file, "line": line,
                    "sql": snippet[:800], "raw_signals": [],
                    "parameterized_signals": [],
                })
        f, u, n = jdbc_features(step, ctx)
        features.extend(f); unknowns.extend(u); neutralizers.extend(n)
    return sites, features, unknowns, neutralizers
