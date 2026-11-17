#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""语义比较：expected.json vs analyzer findings。

不比较完整 JSON。只比较会影响矩阵派发的字段：
state / subtype / CWE / gaps / 关键 file:line / guards / missing。
"""
def _norm(s):
    return str(s or "").replace("\\", "/").lower()


def _file_match(actual, expected):
    a, e = _norm(actual), _norm(expected)
    if not e:
        return True
    return a == e or a.endswith("/" + e) or e in a


def _line_match(actual, expected):
    if expected is None:
        return True
    try:
        return int(actual) == int(expected)
    except Exception:
        return str(actual) == str(expected)


def _actual_sites(finding):
    out = []
    ev = finding.get("evidence") or {}
    for key in ("sites", "resource_accesses", "sql_sites"):
        value = ev.get(key)
        if isinstance(value, list):
            out.extend(value)
    return out


def _actual_gaps(finding):
    ev = finding.get("evidence") or {}
    # authz_model / authn_model / csrf_model / xxe_model / ...
    for key, value in ev.items():
        if key.endswith("_model") and isinstance(value, dict):
            return value.get("gaps") or []
    return ev.get("gaps") or []


def _actual_guards(finding):
    return finding.get("guards_seen") or []


def _match_sites(expected_sites, actual_sites):
    issues = []
    if expected_sites is None:
        return issues
    for want in expected_sites:
        matched = False
        for site in actual_sites:
            if _file_match(site.get("file"), want.get("file")) and _line_match(
                site.get("line"), want.get("line")
            ):
                matched = True
                break
        if not matched:
            issues.append("missing site %s:%s" % (want.get("file"), want.get("line") or "*"))
    return issues


def _match_guards(expected_guards, actual_guards):
    issues = []
    if expected_guards is None:
        return issues
    for want in expected_guards:
        matched = False
        for guard in actual_guards:
            if not _file_match(guard.get("file"), want.get("file")):
                continue
            if want.get("kind") and _norm(guard.get("kind")) != _norm(want.get("kind")):
                continue
            if not _line_match(guard.get("line"), want.get("line")):
                continue
            matched = True
            break
        if not matched:
            issues.append("missing guard %s %s" % (want.get("kind") or "", want.get("file") or ""))
    return issues


def _match_list(expected, actual, label):
    if expected is None:
        return []
    actual_set = set(_norm(x) for x in (actual or []))
    missing = [x for x in expected if _norm(x) not in actual_set]
    if missing:
        return ["missing %s: %s" % (label, ", ".join(str(x) for x in missing))]
    return []


def _check_finding(expected, finding, label):
    issues = []
    actual_state = finding.get("state")
    if expected.get("state") and actual_state != expected.get("state"):
        issues.append("%s state expected %s, got %s" % (label, expected.get("state"), actual_state))
    ev = finding.get("evidence") or {}
    if expected.get("subtype") and ev.get("subtype") != expected.get("subtype"):
        issues.append(
            "%s subtype expected %s, got %s" % (label, expected.get("subtype"), ev.get("subtype"))
        )
    issues.extend(_match_list(expected.get("cwe"), ev.get("cwe"), label + " cwe"))
    issues.extend(_match_list(expected.get("gaps"), _actual_gaps(finding), label + " gaps"))
    issues.extend(_match_sites(expected.get("sites"), _actual_sites(finding)))
    issues.extend(_match_guards(expected.get("guards"), _actual_guards(finding)))
    if expected.get("missing_contains"):
        missing = finding.get("missing") or ""
        if _norm(expected.get("missing_contains")) not in _norm(missing):
            issues.append(
                "%s missing_contains %r, got %r"
                % (label, expected.get("missing_contains"), missing)
            )
    return issues


def compare(expected, findings):
    """返回问题列表；空列表表示通过。"""
    issues = []
    scope = expected.get("scope") or "endpoint"
    vulnclass = expected.get("vulnclass") or ""

    if scope == "repo":
        repo_findings = [f for f in findings if f.get("vulnclass") == vulnclass]
        want_state = expected.get("state") or "possible"
        actual_state = "possible" if repo_findings else "impossible"
        if want_state != actual_state:
            issues.append("repo state expected %s, got %s" % (want_state, actual_state))
            return issues
        if repo_findings:
            issues.extend(_check_finding(expected, repo_findings[0], "repo:" + vulnclass))
        return issues

    endpoints = expected.get("endpoints") or []
    if not endpoints:
        issues.append("expected.json has no endpoints")
        return issues

    for want in endpoints:
        method = (want.get("method") or "").upper()
        url = want.get("url") or ""
        candidates = []
        for f in findings:
            if f.get("vulnclass") != vulnclass:
                continue
            if url and f.get("url") != url:
                continue
            if method and (f.get("method") or "").upper() != method:
                continue
            candidates.append(f)
        label = "%s %s" % (method or "*", url or "*")
        if not candidates:
            issues.append("%s missing finding" % label)
            continue
        issues.extend(_check_finding(want, candidates[0], label))
    return issues
