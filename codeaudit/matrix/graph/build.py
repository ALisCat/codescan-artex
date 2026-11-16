#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图构建器：JavaParser 结构 + Spring 端点 + XML/注解 SQL → graph.json

用法：
  cd codeaudit
  python3 -m matrix.graph.build <源码目录> <输出 graph.json>
可选：
  --callgraph <已有 callgraph.json>   跳过 JavaParser
  --rebuild                           强制重跑 JavaParser
"""
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections import defaultdict, deque
from pathlib import Path

HERE = Path(__file__).resolve()
CODEAUDIT = HERE.parents[2]          # codeaudit/
TOOLS = CODEAUDIT / "tools"
CALLGRAPH_DIR = TOOLS / "callgraph"

FRAMEWORK_BASE_MAPPER = {
    "selectList", "selectOne", "selectById", "selectBatchIds", "selectByMap", "selectCount",
    "selectMaps", "selectObjs", "selectPage", "selectMapsPage",
    "insert", "update", "updateById", "deleteById", "deleteByMap", "delete", "deleteBatchIds",
    "getOne", "list", "listByIds", "listByMap", "page", "count", "save", "saveBatch",
    "updateBatchById", "removeById", "removeByIds",
}
WRAPPER_METHODS = {"eq", "ne", "like", "in", "inSql", "last", "apply", "orderBy", "orderByAsc", "orderByDesc", "having"}


def _load_cellgen():
    spec = importlib.util.spec_from_file_location("cellgen", TOOLS / "cellgen.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_java_sidecar(root: Path, out: Path) -> None:
    java_home = os.environ.get("JAVA_HOME", "")
    java = Path(java_home) / "bin" / "java" if java_home else None
    if not java or not java.exists():
        # 已编译的 class 是 Java 8 兼容的，任意 JRE 8+ 均可运行
        for cand in ("/usr/lib/jvm/java-1.8.0-openjdk-1.8.0.492.b09-1.0.1.an8.x86_64/bin/java",
                     "/usr/lib/jvm/jre-17/bin/java", "/usr/bin/java"):
            if Path(cand).exists():
                java = Path(cand)
                break
    if not java:
        raise SystemExit("找不到 java，可设置 JAVA_HOME")
    jars = sorted((CALLGRAPH_DIR / "lib").glob("*.jar"))
    cp = ":".join(str(p) for p in jars) + ":" + str(CALLGRAPH_DIR)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(java), "-Xmx3g", "-cp", cp, "CallGraphDump", str(root), str(out)],
                   cwd=str(CALLGRAPH_DIR), check=True)


class GraphBuilder:
    def __init__(self, root: Path, callgraph: dict, cellgen):
        self.root = root
        self.cg = callgraph
        self.cellgen = cellgen
        self.methods = {m["id"]: m for m in callgraph["methods"]}
        self.classes = {c["fqn"]: c for c in callgraph["classes"]}
        self.calls = callgraph["calls"]
        self.fields = callgraph["fields"]

        self.simple = defaultdict(list)
        for fqn in self.classes:
            self.simple[fqn.split(".")[-1]].append(fqn)

        self.calls_by = defaultdict(list)
        for c in self.calls:
            self.calls_by[c["caller"]].append(c)

        self.adj = defaultdict(list)
        for c in self.calls:
            if c["resolved"] and c["callee"]:
                self.adj[c["caller"]].append(c["callee"])

        self.impls = defaultdict(set)
        for fqn, c in self.classes.items():
            for i in c.get("implements", []):
                self.impls[self.resolve_simple(i.split("<")[0])].add(fqn)
            for e in c.get("extends", []):
                self.impls[self.resolve_simple(e.split("<")[0])].add(fqn)

        self.field_type = {(f["cls"], f["name"]): f["type"] for f in self.fields}
        self.methods_by_cls = defaultdict(list)
        for m in callgraph["methods"]:
            self.methods_by_cls[(m["cls"], m["name"])].append(m)
        self.base_mapper = {}
        for c in callgraph["classes"]:
            for e in c.get("extends", []):
                m = re.search(r"ServiceImpl\s*<\s*([^,>]+)", e)
                if m:
                    self.base_mapper[c["fqn"]] = self.resolve_simple(m.group(1))

        self.xml_sites = self._load_xml()
        self.endpoints = self._load_endpoints()
        self.ann_sites = self._load_annotations()

    def resolve_simple(self, name: str) -> str:
        name = (name or "").strip()
        if name in self.classes:
            return name
        cand = self.simple.get(name.split(".")[-1])
        return cand[0] if cand else name

    def _load_xml(self) -> dict:
        sites = {}
        base = self.root / "src" / "main" / "resources"
        if not base.exists():
            return sites
        for p in base.rglob("*.xml"):
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            ns = re.search(r'<mapper\s+namespace="([^"]+)"', txt)
            if not ns:
                continue
            for m in re.finditer(r"<(select|insert|update|delete)\s+id=\"([^\"]+)\"[^>]*>(.*?)</\1>", txt, re.S):
                sites[(ns.group(1), m.group(2))] = {
                    "kind": "xml", "file": str(p.relative_to(self.root)),
                    "line": txt.count("\n", 0, m.start()) + 1,
                    "sql": m.group(3).strip()[:1200],
                }
        return sites

    def _load_annotations(self) -> dict:
        sites = defaultdict(list)
        for name, items in (getattr(self, "ann_map", {}) or {}).items():
            for text, f, line in items:
                try:
                    rel = str(Path(f).relative_to(self.root))
                except Exception:
                    rel = str(f)
                sites[name].append({"kind": "annotation", "file": rel, "line": line, "sql": str(text)[:1200]})
        return sites

    def _load_endpoints(self) -> list:
        self.cellgen.ROOT = str(self.root)
        clean, masked, raws, xml_map, ann_map, idx, proj = self.cellgen.parse_project(str(self.root))
        self.ann_map = ann_map
        self.xml_map = xml_map
        eps = self.cellgen.endpoints(clean, masked, idx, raws)
        out = []
        for ep in eps:
            try:
                rel = str(Path(ep["file"]).relative_to(self.root))
            except Exception:
                rel = str(ep["file"])
            out.append({
                "method": ep["http"], "url": ep["url"], "handler": ep["handler"],
                "file": rel, "line": ep["line"],
                "params": ep.get("params") or [],
                "bline": ep.get("bline", ep["line"]),
            })
        return out

    def find_handler(self, ep):
        cands = [m for m in self.methods.values()
                 if m["name"] == ep["handler"] and m["file"].endswith(ep["file"])]
        if not cands:
            return None
        return min(cands, key=lambda m: abs(m["line"] - ep.get("line", 0)))

    def impl_methods(self, iface_method):
        m = self.methods.get(iface_method)
        if not m:
            return []
        out = []
        for impl in self.impls.get(m["cls"], []):
            for cand in self.methods.values():
                if cand["cls"] == impl and cand["name"] == m["name"] and len(cand["params"]) == len(m["params"]):
                    out.append(cand["id"])
        return out

    def fallback_call(self, caller_cls, call):
        """JavaParser 因实参类型未解析（Lombok getter / 外部类型）而 resolve 失败时，
        用 接收者类型 + 方法名 + 参数个数 回退。"""
        st = (call.get("scopeText") or "").strip()
        t = (call.get("scope") or "").strip()
        if not t and st:
            t = self.field_type.get((caller_cls, st), "")
        t = self.resolve_simple(t.split("<")[0]) if t else ""
        if not t:
            # 无接收者：先按本类/父类的方法解析（checkOwner 这类私有 helper）
            t = caller_cls
        seen = set()
        out = []
        while t and t not in seen:
            seen.add(t)
            cands = [m for m in self.methods_by_cls.get((t, call["name"]), [])
                     if len(m["params"]) == call.get("argc", -1)]
            if len(cands) == 1:
                return [cands[0]["id"]]
            out += [m["id"] for m in cands]
            for impl in self.impls.get(t, []):
                cc = [m for m in self.methods_by_cls.get((impl, call["name"]), [])
                      if len(m["params"]) == call.get("argc", -1)]
                out += [m["id"] for m in cc]
            ext = (self.classes.get(t) or {}).get("extends") or []
            t = self.resolve_simple(ext[0].split("<")[0]) if ext else ""
        return out

    @staticmethod
    def _is_dao(fqn):
        if not fqn:
            return False
        short = fqn.split(".")[-1]
        if short.lower() in ("objectmapper", "modelmapper", "beanmapper", "dozermapper"):
            return False
        if fqn.startswith(("com.fasterxml.", "org.modelmapper.", "org.dozer.")):
            return False
        return bool(re.search(r"(Mapper|Dao|Repository)$", short))

    def dao_hit(self, caller_cls, call):
        name = call["name"]
        st = (call.get("scopeText") or "").strip()
        if st:
            ty = self.field_type.get((caller_cls, st))
            if ty and self._is_dao(ty.split("<")[0]):
                return self.resolve_simple(ty.split("<")[0]), name
            if self._is_dao(st.split(".")[-1]):
                return self.resolve_simple(st.split(".")[-1]), name
        bm = self.base_mapper.get(caller_cls)
        if bm and name in FRAMEWORK_BASE_MAPPER:
            return bm, name
        sc = (call.get("scope") or "").strip()
        if sc and self._is_dao(sc.split("<")[0]):
            return self.resolve_simple(sc.split("<")[0]), name
        return None

    def build_endpoint(self, ep):
        hm = self.find_handler(ep)
        if not hm:
            return None
        flow, daos, unresolved = [], [], []
        q = deque([(hm["id"], 1)])
        seen = set()
        while q and len(flow) < 200:
            mid, depth = q.popleft()
            if mid in seen or depth > 12:
                continue
            seen.add(mid)
            m = self.methods.get(mid)
            if not m:
                continue
            flow.append({
                "method_id": mid, "cls": m["cls"], "name": m["name"],
                "file": m["file"], "line": m["line"], "end": m.get("end", m["line"]),
                "kind": "method",
            })
            for call in self.calls_by.get(mid, []):
                hit = self.dao_hit(m["cls"], call)
                if hit:
                    dao_cls, dao_name = hit
                    site = self.xml_sites.get((dao_cls, dao_name))
                    wrapper = [w for w in self.calls_by.get(mid, []) if w.get("scopeText") and w["name"] in WRAPPER_METHODS]
                    if site is None:
                        ann = self.ann_sites.get(dao_name)
                        if ann:
                            site = ann[0]
                    if site:
                        sql_kind = site["kind"]
                    elif wrapper:
                        sql_kind = "wrapper"
                    else:
                        sql_kind = "unknown"
                    daos.append({
                        "dao": dao_cls, "method": dao_name, "sql_kind": sql_kind,
                        "sql_site": site,
                        "wrapper": [{"name": w["name"], "file": w["file"], "line": w["line"],
                                     "scope": w.get("scopeText", "")} for w in wrapper],
                        "call_file": m["file"], "call_line": call["line"],
                    })
                    flow.append({
                        "kind": "dao", "cls": dao_cls, "name": dao_name,
                        "file": m["file"], "line": call["line"], "end": call["line"],
                        "sql_kind": sql_kind,
                    })
                    continue
                nxt = []
                if call["resolved"] and call["callee"]:
                    nxt = [call["callee"]]
                if not nxt:
                    nxt = self.fallback_call(m["cls"], call)
                expanded = []
                for n in nxt:
                    expanded.append(n)
                    expanded.extend(self.impl_methods(n))
                if expanded:
                    for n in expanded:
                        if n not in seen:
                            q.append((n, depth + 1))
                else:
                    unresolved.append({
                        "caller_cls": m["cls"],
                        "file": call["file"], "line": call["line"], "name": call["name"],
                        "scope": call.get("scope", ""), "scopeText": call.get("scopeText", ""),
                    })
        return {
            "id": f"{ep['method']} {ep['url']}", "url": ep["url"], "method": ep["method"],
            "handler": ep["handler"], "file": ep["file"], "line": ep["line"],
            "params": ep["params"], "flow": flow, "daos": daos,
            "unresolved": unresolved[:30],
        }

    def build(self):
        endpoints = []
        for ep in self.endpoints:
            e = self.build_endpoint(ep)
            if e:
                endpoints.append(e)
        return {
            "version": "1.0",
            "root": str(self.root),
            "stats": {
                "endpoints": len(endpoints),
                "flow_steps": sum(len(e["flow"]) for e in endpoints),
                "endpoints_with_dao": sum(1 for e in endpoints if e["daos"]),
                "unresolved_calls": sum(len(e["unresolved"]) for e in endpoints),
            },
            "endpoints": endpoints,
            "classes": self.cg["classes"],
            "fields": self.cg["fields"],
            "methods": self.cg["methods"],
            "calls": self.cg["calls"],
            "xml_sites": [
                {"dao": k[0], "method": k[1], **v} for k, v in sorted(self.xml_sites.items())
            ],
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("out")
    ap.add_argument("--callgraph")
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    out = Path(args.out).resolve()

    cg_path = Path(args.callgraph) if args.callgraph else out.with_suffix(".callgraph.json")
    if args.rebuild or not cg_path.exists():
        run_java_sidecar(root, cg_path)
    cg = json.loads(cg_path.read_text(encoding="utf-8"))

    cellgen = _load_cellgen()
    builder = GraphBuilder(root, cg, cellgen)
    graph = builder.build()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(graph, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(graph["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()
