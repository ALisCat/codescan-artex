"use client";

// 二开：审计矩阵（接口 × 漏洞类型）看板 v3。
//
// 目标（v3）：
//   1. 单元格直接写人话：会派 / 已派 / 守卫 / 未验 / 漏洞 / 通过 / 待定
//   2. 点接口名 → 右侧抽屉看该接口全部类型：哪些会派、哪些有守卫、原因是什么
//   3. 点格子 → 右侧抽屉看该格详情，不用滚到页面底部
//   4. 长矩阵窗口化渲染（固定行高 + 可视区切片），1000+ 行不卡
//   5. 筛选：会派发 / 有守卫 / 已确认 / 未验证 / 有结论
//
// 颜色口径：
//   蓝=会派(pending) 黄=已派(dispatched) 红=confirmed 绿=clean 紫=needs_more
//   琥珀虚线=hold(有守卫，不派) 灰虚线=unverified(未验证，不派) 灰=na

import * as React from "react";
import {
  BugIcon,
  CircleCheckIcon,
  CircleHelpIcon,
  Loader2Icon,
  MinusIcon,
  ShieldCheckIcon,
} from "lucide-react";

import { api } from "@/lib/api";
import type { CaCell, CaStats } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

type VulnDef = { key: string; label: string };

const VULNS: VulnDef[] = [
  { key: "authz", label: "越权" },
  { key: "authn", label: "认证/回调" },
  { key: "sql-injection", label: "SQLi" },
  { key: "command-exec", label: "命令/表达式" },
  { key: "ssrf", label: "SSRF" },
  { key: "deserialization", label: "反序列化" },
  { key: "file-upload", label: "文件上传" },
  { key: "path-traversal", label: "路径穿越" },
  { key: "xss", label: "XSS" },
  { key: "business_logic", label: "业务逻辑" },
  { key: "xxe", label: "XXE" },
  { key: "csrf", label: "CSRF" },
  { key: "open_redirect", label: "开放重定向" },
  { key: "ssti", label: "SSTI" },
  { key: "ldap_injection", label: "LDAP" },
  { key: "mass_assignment", label: "批量赋值" },
  { key: "race_condition", label: "竞态" },
  { key: "secrets", label: "硬编码凭据" },
  { key: "crypto", label: "弱加密" },
  { key: "dependency", label: "依赖漏洞" },
  { key: "sensitive_data", label: "敏感数据" },
];

// 已知类型用中文短名；后续新增类型即使前端还没登记，也先按 key 展示，避免丢列。
function mergeVulns(keys: string[]): VulnDef[] {
  const out = new Map<string, VulnDef>();
  for (const v of VULNS) out.set(v.key, v);
  for (const k of keys) {
    if (!out.has(k)) out.set(k, { key: k, label: k });
  }
  return [...out.values()];
}

type StatusMeta = { label: string; short: string; cell: string; dot: string; hint: string };

const STATUS_META: Record<string, StatusMeta> = {
  na: {
    label: "不适用",
    short: "·",
    cell: "border-transparent bg-transparent text-muted-foreground/25",
    dot: "border border-dashed border-muted-foreground/30 bg-transparent",
    hint: "结构上不可能：没有该类型的入口/参数",
  },
  hold: {
    label: "有守卫（不派）",
    short: "守卫",
    cell: "border-dashed border-amber-400/50 bg-amber-400/10 text-amber-700 dark:text-amber-300",
    dot: "border border-dashed border-amber-400/60 bg-amber-400/15",
    hint: "已有归属校验 / 参数化 / 路径限制等守卫：保留可见，但不派单",
  },
  hold_low: {
    label: "低置信（不派）",
    short: "低信",
    cell: "border-dashed border-slate-400/50 bg-slate-400/10 text-slate-600 dark:text-slate-300",
    dot: "border border-dashed border-slate-400/50 bg-slate-400/15",
    hint: "命名/注释信号不足，默认不派单；可在矩阵里看到，需要时手动派",
  },
  unverified: {
    label: "未知/未验证（不派）",
    short: "未验",
    cell: "border-dashed border-slate-400/50 bg-slate-500/10 text-slate-600 dark:text-slate-300",
    dot: "border border-dashed border-slate-400/50 bg-slate-500/15",
    hint: "图不完整（未解析调用/缺 DAO），无法确认该类 sink 是否存在",
  },
  pending: {
    label: "会派发",
    short: "会派",
    cell: "border-blue-500/50 bg-blue-500/15 text-blue-700 dark:text-blue-300",
    dot: "border border-blue-500/50 bg-blue-500/25",
    hint: "结构可达且没有已知守卫 → 已进入 worker 队列",
  },
  dispatched: {
    label: "已派（审查中）",
    short: "已派",
    cell: "border-amber-500/50 bg-amber-500/20 text-amber-700 dark:text-amber-300",
    dot: "border border-amber-500/60 bg-amber-500/30",
    hint: "已生成意图：排队中或正在审；会消耗 worker/LLM",
  },
  confirmed: {
    label: "已确认漏洞",
    short: "漏洞",
    cell: "border-red-500/60 bg-red-500/20 text-red-700 dark:text-red-300",
    dot: "border border-red-500/60 bg-red-500/35",
    hint: "worker 已确认并登记 finding",
  },
  clean: {
    label: "已排除",
    short: "通过",
    cell: "border-emerald-500/50 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
    dot: "border border-emerald-500/60 bg-emerald-500/30",
    hint: "worker 给出了正向证据，判定不存在该风险",
  },
  needs_more: {
    label: "待补充证据",
    short: "待定",
    cell: "border-violet-500/50 bg-violet-500/15 text-violet-700 dark:text-violet-300",
    dot: "border border-violet-500/60 bg-violet-500/30",
    hint: "worker 判不了：缺证据或需要外部确认",
  },
  failed: {
    label: "失败",
    short: "失败",
    cell: "border-red-900/60 bg-red-900/20 text-red-800 dark:text-red-300",
    dot: "border border-red-900/70 bg-red-900/40",
    hint: "重试次数用尽",
  },
};

// 图例顺序：先看"会派/结果"，再看"没派"
const LEGEND = ["pending", "dispatched", "confirmed", "clean", "needs_more", "hold", "hold_low", "unverified", "failed", "na"];

const STATUS_RANK: Record<string, number> = {
  confirmed: 8,
  needs_more: 7,
  failed: 6,
  dispatched: 5,
  pending: 4,
  clean: 3,
  unverified: 2,
  hold: 1,
  na: 0,
};

type RowData = {
  key: string;
  method: string;
  url: string;
  cells: Map<string, CaCell>;
  counts: Record<string, number>;
  guard: number;
  low: number;
  weight: number;
};

function summaryStatus(r: RowData): { key: string; label: string; cls: string } {
  if ((r.counts.confirmed ?? 0) > 0) {
    return { key: "confirmed", label: "已确认", cls: "border-red-500/50 bg-red-500/10 text-red-700 dark:text-red-300" };
  }
  if ((r.counts.needs_more ?? 0) > 0) {
    return { key: "needs_more", label: "待补充", cls: "border-violet-500/50 bg-violet-500/10 text-violet-700 dark:text-violet-300" };
  }
  if ((r.counts.pending ?? 0) + (r.counts.dispatched ?? 0) > 0) {
    return { key: "pending", label: "待审", cls: "border-blue-500/50 bg-blue-500/10 text-blue-700 dark:text-blue-300" };
  }
  if ((r.counts.clean ?? 0) > 0) {
    return { key: "clean", label: "已排除", cls: "border-emerald-500/50 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" };
  }
  if ((r.counts.unverified ?? 0) > 0) {
    return { key: "unverified", label: "未验证", cls: "border-slate-400/50 bg-slate-500/10 text-slate-600 dark:text-slate-300" };
  }
  return { key: "none", label: "—", cls: "border-border text-muted-foreground" };
}

function summaryText(r: RowData, allVulns: VulnDef[]): string {
  const labels = (status: string) =>
    allVulns.filter((v) => r.cells.get(v.key)?.status === status).map((v) => v.label);
  const confirmed = labels("confirmed");
  const pending = [...labels("pending"), ...labels("dispatched")];
  const needs = labels("needs_more");
  const clean = labels("clean");
  const unverified = labels("unverified");
  const fmt = (xs: string[]) => {
    const head = xs.slice(0, 3).join("、");
    return xs.length > 3 ? `${head} 等` : head;
  };

  if (confirmed.length > 0) {
    let s = `发现 ${confirmed.length} 个：${fmt(confirmed)}`;
    if (pending.length > 0) s += `；另有 ${pending.length} 类待审`;
    if (unverified.length > 0) s += `；${unverified.length} 类未验证`;
    return s;
  }
  if (pending.length > 0) {
    let s = `待审 ${pending.length} 类：${fmt(pending)}`;
    if (needs.length > 0) s += `；${needs.length} 类待补充`;
    if (unverified.length > 0) s += `；${unverified.length} 类未验证`;
    return s;
  }
  if (needs.length > 0) return `待补充 ${needs.length} 类：${fmt(needs)}`;
  if (clean.length > 0) return `已排除 ${clean.length} 类，无确认漏洞`;
  if (unverified.length > 0) return `未验证 ${unverified.length} 类`;
  return "暂无判定结果";
}

function summaryBucket(r: RowData): { label: string; cls: string } {
  if (r.weight <= 0) return { label: "—", cls: "text-muted-foreground" };
  if (r.weight >= 20) return { label: "P0", cls: "text-red-600 dark:text-red-400" };
  if (r.weight >= 14) return { label: "P1", cls: "text-amber-600 dark:text-amber-400" };
  return { label: "P2", cls: "text-slate-600 dark:text-slate-300" };
}

type FilterKind = "all" | "dispatch" | "hold" | "confirmed" | "unverified" | "done";
type DisplayMode = "summary" | "matrix";

const FILTERS: { key: FilterKind; label: string }[] = [
  { key: "all", label: "全部（有内容）" },
  { key: "dispatch", label: "只看会派发" },
  { key: "hold", label: "只看有守卫" },
  { key: "confirmed", label: "只看确认漏洞" },
  { key: "unverified", label: "只看未验证" },
  { key: "done", label: "只看有结论" },
];

const ROW_H = 34;
const SUMMARY_ROW_H = 58;
const OVERSCAN = 8;
const SUMMARY_GRID = "minmax(260px, 2.4fr) 72px 96px minmax(300px, 3fr) 72px";

function rowMatches(r: RowData, kind: FilterKind): boolean {
  const has = (s: string) => (r.counts[s] ?? 0) > 0;
  switch (kind) {
    case "dispatch":
      return has("pending") || has("dispatched");
    case "hold":
      return has("hold");
    case "confirmed":
      return has("confirmed");
    case "unverified":
      return has("unverified");
    case "done":
      return has("confirmed") || has("clean") || has("needs_more");
    default:
      return Object.keys(r.counts).some((s) => s !== "na");
  }
}

function metaFor(c?: CaCell): StatusMeta {
  if (!c) return STATUS_META.na;
  if (c.status === "hold" && (c.reason ?? "").includes("低置信")) return STATUS_META.hold_low;
  return STATUS_META[c.status] ?? STATUS_META.na;
}

function prefixOf(url: string) {
  const parts = url.split("?")[0].split("/").filter(Boolean);
  return "/" + parts.slice(0, 2).join("/");
}

function pretty(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

function useVirtualRows(count: number, rowHeight: number, ref: React.RefObject<HTMLDivElement | null>) {
  const [range, setRange] = React.useState({ start: 0, end: 30 });
  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const calc = () => {
      raf = 0;
      const top = el.scrollTop;
      const h = el.clientHeight || 600;
      const start = Math.max(0, Math.floor(top / rowHeight) - OVERSCAN);
      const end = Math.min(count, Math.ceil((top + h) / rowHeight) + OVERSCAN);
      setRange((prev) => (prev.start === start && prev.end === end ? prev : { start, end }));
    };
    calc();
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(calc);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    const ro = new ResizeObserver(calc);
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", onScroll);
      if (raf) cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [count, rowHeight, ref]);
  return range;
}

export function MatrixTab({ taskId }: { taskId: string }) {
  const [cells, setCells] = React.useState<CaCell[]>([]);
  const [stats, setStats] = React.useState<CaStats | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [tick, setTick] = React.useState(0);
  const reload = React.useCallback(() => setTick((x) => x + 1), []);

  const [q, setQ] = React.useState("");
  const [displayMode, setDisplayMode] = React.useState<DisplayMode>("summary");
  const [view, setView] = React.useState<"endpoint" | "prefix">("endpoint");
  const [kind, setKind] = React.useState<FilterKind>("all");
  const [showNaRows, setShowNaRows] = React.useState(false);
  const [showAllVulns, setShowAllVulns] = React.useState(false);

  const [cellSel, setCellSel] = React.useState<CaCell | null>(null);
  const [endpointKey, setEndpointKey] = React.useState<string | null>(null);

  const scrollRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    let active = true;
    const load = () =>
      Promise.all([api.caCells(taskId), api.caStats(taskId)])
        .then(([cs, st]) => {
          if (!active) return;
          setCells(cs);
          setStats(st);
          setErr(null);
        })
        .catch((e) => {
          if (active) setErr(String(e?.message ?? e));
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    void load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [taskId, tick]);

  React.useEffect(() => {
    setCellSel((prev) => {
      if (!prev) return prev;
      return cells.find((c) => c.id === prev.id) ?? prev;
    });
  }, [cells]);

  const { allRows, rowMap } = React.useMemo(() => {
    const m = new Map<string, RowData>();
    for (const c of cells) {
      const key = `${c.method} ${c.endpoint_url}`;
      let r = m.get(key);
      if (!r) {
        r = { key, method: c.method, url: c.endpoint_url, cells: new Map(), counts: {}, guard: 0, low: 0, weight: 0 };
        m.set(key, r);
      }
      r.cells.set(c.vulnclass, c);
      r.counts[c.status] = (r.counts[c.status] ?? 0) + 1;
      if (c.status === "hold") {
        if ((c.reason ?? "").includes("低置信")) r.low += 1;
        else r.guard += 1;
      }
      if (c.status !== "na") r.weight = Math.max(r.weight, c.priority ?? 0);
    }
    return { allRows: [...m.values()], rowMap: m };
  }, [cells]);

  const rows = React.useMemo(() => {
    const ql = q.trim().toLowerCase();
    let rs = allRows.filter((r) => {
      if (ql && !r.key.toLowerCase().includes(ql)) return false;
      if (!showNaRows && !rowMatches(r, "all")) return false;
      return rowMatches(r, kind);
    });
    rs = rs.sort((a, b) => {
      const ca = a.counts.confirmed ?? 0;
      const cb = b.counts.confirmed ?? 0;
      if (ca !== cb) return cb - ca;
      const da = (a.counts.pending ?? 0) + (a.counts.dispatched ?? 0);
      const db = (b.counts.pending ?? 0) + (b.counts.dispatched ?? 0);
      if (da !== db) return db - da;
      if (a.weight !== b.weight) return b.weight - a.weight;
      return a.key.localeCompare(b.key);
    });
    return rs;
  }, [allRows, q, kind, showNaRows]);

  const allVulns = React.useMemo(
    () => mergeVulns(cells.map((c) => c.vulnclass)),
    [cells],
  );

  // 表格默认只给“有分析结果”的类型留列：
  // possible/pending/dispatched/confirmed/clean/needs_more/hold 都算；
  // na（结构上不可能）和 unverified（未验证）默认收进右侧抽屉。
  const visibleVulns = React.useMemo(() => {
    if (showAllVulns || cells.length === 0) return allVulns;
    const keep = new Set(
      cells
        .filter((c) => c.status !== "na" && c.status !== "unverified")
        .map((c) => c.vulnclass),
    );
    return allVulns.filter((v) => keep.has(v.key));
  }, [allVulns, cells, showAllVulns]);
  const hiddenVulnCount = allVulns.length - visibleVulns.length;
  const tableVulns = React.useMemo(
    () => (visibleVulns.length > 0 ? visibleVulns : [{ key: "__none__", label: "—" }]),
    [visibleVulns],
  );
  const gridTemplate = React.useMemo(
    () =>
      `minmax(230px, 2.2fr) repeat(${tableVulns.length}, minmax(58px, 1fr)) minmax(112px, 0.9fr)`,
    [tableVulns.length],
  );
  const gridMinWidth = Math.max(900, 360 + tableVulns.length * 64);

  // 前缀聚合
  const grouped = React.useMemo(() => {
    if (view !== "prefix") return null;
    const m = new Map<string, Map<string, { worst: string; count: number }>>();
    for (const r of rows) {
      const p = prefixOf(r.url);
      if (!m.has(p)) m.set(p, new Map());
      const g = m.get(p)!;
      for (const v of tableVulns) {
        const c = r.cells.get(v.key);
        if (!c || c.status === "na") continue;
        const cur = g.get(v.key);
        if (!cur) g.set(v.key, { worst: c.status, count: 1 });
        else {
          cur.count += 1;
          if ((STATUS_RANK[c.status] ?? 0) > (STATUS_RANK[cur.worst] ?? 0)) cur.worst = c.status;
        }
      }
    }
    return m;
  }, [view, rows, tableVulns]);

  React.useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0 });
  }, [q, kind, view, showNaRows, displayMode]);

  const by = stats?.by_status ?? {};
  const dispatchCount = (by.pending ?? 0) + (by.dispatched ?? 0);
  const doneCount = (by.confirmed ?? 0) + (by.clean ?? 0) + (by.needs_more ?? 0);

  const summaryView = displayMode === "summary";
  const virtual = useVirtualRows(
    summaryView ? rows.length : view === "endpoint" ? rows.length : 0,
    summaryView ? SUMMARY_ROW_H : ROW_H,
    scrollRef,
  );
  const visibleRows = summaryView || view === "endpoint" ? rows.slice(virtual.start, virtual.end) : [];

  const endpointRow = endpointKey ? rowMap.get(endpointKey) ?? null : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
        <Stat label="矩阵格数" value={stats?.total ?? 0} />
        <Stat label="会派发" value={dispatchCount} tone="blue" />
        <Stat label="已派发" value={by.dispatched ?? 0} tone="amber" />
        <Stat label="未派（守卫/低置信）" value={stats?.hold ?? 0} tone="amber" />
        <Stat label="未知/未验证" value={stats?.unverified ?? 0} tone="muted" />
        <Stat label="确认漏洞" value={by.confirmed ?? 0} tone="red" />
        <Stat label="已排除" value={by.clean ?? 0} tone="emerald" />
        <Stat label="不适用" value={stats?.not_applicable ?? 0} tone="muted" />
      </div>

      <Card>
        <CardHeader className="gap-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle className="flex items-center gap-2 text-sm">
                <BugIcon className="size-4" /> {summaryView ? "接口审计摘要" : "接口 × 漏洞类型"}
                {loading && <Loader2Icon className="size-3.5 animate-spin text-muted-foreground" />}
                <span className="text-xs font-normal text-muted-foreground">
                  {doneCount > 0 ? `已了结 ${doneCount} 格` : "等待 worker 回填"}
                </span>
              </CardTitle>
              <p className="max-w-4xl text-[11px] leading-5 text-muted-foreground">
                {summaryView ? (
                  <>
                    摘要视图：一行一个接口，直接看<b>已确认 / 待审 / 已排除 / 未验证</b>。
                    点<b>接口名</b>或<b>查看</b>打开右侧抽屉，里面保留该接口全部 {allVulns.length} 类的完整判定。
                  </>
                ) : (
                  <>
                    <b>会派</b>=结构可达且无已知守卫，已进入 worker 队列；
                    <b>守卫</b>=有归属/参数化/路径校验，保留可见但不派；
                    <b>未验</b>=调用链没解析全，无法确认。
                    点<b>接口名</b>看该接口全部 {allVulns.length} 类，点<b>格子</b>看该格详情。
                    表格默认只显示有分析结果的类型；N/A 和未验证收进接口抽屉。
                  </>
                )}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
              {LEGEND.map((k) => (
                <span key={k} className="flex items-center gap-1" title={STATUS_META[k]?.hint}>
                  <span className={cn("inline-block size-2.5 rounded-sm", STATUS_META[k].dot)} />
                  {STATUS_META[k].label}
                </span>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜索接口 / 前缀，如 /api/appointment"
              className="h-8 w-64 rounded border bg-background px-2"
            />
            <div className="flex rounded border">
              <button
                type="button"
                onClick={() => setDisplayMode("summary")}
                className={cn("px-2 py-1", summaryView && "bg-primary/10 font-medium text-primary")}
              >
                摘要
              </button>
              <button
                type="button"
                onClick={() => setDisplayMode("matrix")}
                className={cn("px-2 py-1", !summaryView && "bg-primary/10 font-medium text-primary")}
              >
                矩阵
              </button>
            </div>
            {!summaryView && (
              <div className="flex rounded border">
                <button
                  type="button"
                  onClick={() => setView("endpoint")}
                  className={cn("px-2 py-1", view === "endpoint" && "bg-primary/10 font-medium text-primary")}
                >
                  接口级
                </button>
                <button
                  type="button"
                  onClick={() => setView("prefix")}
                  className={cn("px-2 py-1", view === "prefix" && "bg-primary/10 font-medium text-primary")}
                >
                  前缀聚合
                </button>
              </div>
            )}
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as FilterKind)}
              className="h-8 rounded border bg-background px-2"
            >
              {FILTERS.map((f) => (
                <option key={f.key} value={f.key}>
                  {f.label}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-1 text-muted-foreground">
              <input
                type="checkbox"
                checked={showNaRows}
                onChange={(e) => setShowNaRows(e.target.checked)}
              />
              显示全不适用行
            </label>
            {!summaryView && (
              <label className="flex items-center gap-1 text-muted-foreground">
                <input
                  type="checkbox"
                  checked={showAllVulns}
                  onChange={(e) => setShowAllVulns(e.target.checked)}
                />
                显示全部类型
              </label>
            )}
            {!summaryView && (
              <span className="text-muted-foreground">
                覆盖 {allVulns.length} 类 · 显示 {visibleVulns.length} 类
                {hiddenVulnCount > 0 ? ` · 隐藏 ${hiddenVulnCount} 类（N/A/未验）` : ""}
              </span>
            )}
            <span className="text-muted-foreground">
              行 {!summaryView && view === "prefix" ? grouped?.size ?? 0 : rows.length}
              {(summaryView || view === "endpoint") && rows.length > visibleRows.length
                ? `（已渲染 ${visibleRows.length}）`
                : ""}
            </span>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          {err && <p className="px-4 pt-2 text-xs text-destructive">{err}</p>}
          <div ref={scrollRef} className="max-h-[68vh] min-h-[340px] overflow-auto overscroll-contain border-t">
            <div style={{ minWidth: summaryView ? 900 : gridMinWidth }}>
              {summaryView && (
                <>
                  <div
                    className="sticky top-0 z-20 grid h-9 items-center border-b bg-background px-2 text-[11px] font-medium"
                    style={{ gridTemplateColumns: SUMMARY_GRID }}
                  >
                    <div>接口</div>
                    <div className="text-center">优先级</div>
                    <div className="text-center">状态</div>
                    <div>摘要</div>
                    <div className="text-center">操作</div>
                  </div>
                  <div style={{ height: virtual.start * SUMMARY_ROW_H }} />
                  {visibleRows.map((r) => (
                    <SummaryRow
                      key={r.key}
                      r={r}
                      allVulns={allVulns}
                      onOpen={() => setEndpointKey(r.key)}
                    />
                  ))}
                  <div style={{ height: Math.max(0, rows.length - virtual.end) * SUMMARY_ROW_H }} />
                </>
              )}

              {!summaryView && (
                <>
              {/* 表头 */}
              <div
                className="sticky top-0 z-20 grid h-9 items-center border-b bg-background text-[11px] font-medium"
                style={{ gridTemplateColumns: gridTemplate }}
              >
                <div className="sticky left-0 z-30 flex h-full items-center bg-background px-2">
                  {view === "prefix" ? "前缀" : "接口"}
                </div>
                {tableVulns.map((v) => (
                  <div key={v.key} className="truncate px-1 text-center" title={v.key}>
                    {v.label}
                  </div>
                ))}
                <div className="px-2 text-center">本行汇总</div>
              </div>

              {view === "endpoint" && (
                <>
                  <div style={{ height: virtual.start * ROW_H }} />
                  {visibleRows.map((r) => (
                    <div
                      key={r.key}
                      className="grid items-center border-b border-border/60 hover:bg-muted/30"
                      style={{ gridTemplateColumns: gridTemplate, height: ROW_H }}
                    >
                      <button
                        type="button"
                        onClick={() => setEndpointKey(r.key)}
                        className="sticky left-0 z-10 flex h-full min-w-0 items-center gap-2 bg-background px-2 text-left hover:bg-muted/40"
                        title="查看该接口全部漏洞类型"
                      >
                        <Badge variant="outline" className="shrink-0 px-1 py-0 font-mono text-[9px]">
                          {r.method}
                        </Badge>
                        <span className="truncate font-mono text-[11px]">{r.url}</span>
                      </button>
                      {tableVulns.map((v) => {
                        const c = r.cells.get(v.key);
                        const meta = metaFor(c);
                        return (
                          <div key={v.key} className="px-0.5">
                            <button
                              type="button"
                              title={
                                c
                                  ? `${v.label} · ${meta.label} · P${c.priority}${c.status === "na" ? "（点击可人工发起审计）" : ""}\n${c.reason || meta.hint}`
                                  : `${v.label} · 不适用`
                              }
                              onClick={() => c && setCellSel(c)}
                              className={cn(
                                "h-6 w-full truncate rounded border px-0.5 text-[10px] font-medium transition",
                                meta.cell,
                                !c && "cursor-default opacity-30",
                                c && "hover:brightness-110",
                              )}
                            >
                              {meta.short}
                            </button>
                          </div>
                        );
                      })}
                      <RowSummary r={r} onClick={() => setEndpointKey(r.key)} />
                    </div>
                  ))}
                  <div style={{ height: Math.max(0, rows.length - virtual.end) * ROW_H }} />
                </>
              )}

              {view === "prefix" &&
                [...(grouped?.keys() ?? [])].sort().map((p) => {
                  const g = grouped!.get(p)!;
                  return (
                    <div
                      key={p}
                      className="grid items-center border-b border-border/60 hover:bg-muted/30"
                      style={{ gridTemplateColumns: gridTemplate, height: ROW_H }}
                    >
                      <button
                        type="button"
                        onClick={() => {
                          setQ(p);
                          setView("endpoint");
                        }}
                        className="sticky left-0 z-10 flex h-full min-w-0 items-center bg-background px-2 text-left font-mono text-[11px] hover:bg-muted/40"
                        title="下钻到该前缀的接口"
                      >
                        {p}
                      </button>
                      {tableVulns.map((v) => {
                        const agg = g.get(v.key);
                        const st = agg?.worst ?? "na";
                        const meta = STATUS_META[st] ?? STATUS_META.na;
                        return (
                          <div key={v.key} className="px-0.5">
                            <button
                              type="button"
                              title={agg ? `${agg.count} 个接口 · 最重状态：${meta.label}` : "无"}
                              onClick={() => {
                                setQ(p);
                                setView("endpoint");
                              }}
                              className={cn(
                                "h-6 w-full rounded border text-[10px] font-medium",
                                meta.cell,
                                !agg && "cursor-default opacity-30",
                              )}
                            >
                              {agg ? agg.count : ""}
                            </button>
                          </div>
                        );
                      })}
                      <div className="px-2 text-center text-[10px] text-muted-foreground">
                        {g.size > 0 ? `${g.size} 类有内容` : "—"}
                      </div>
                    </div>
                  );
                })}
                </>
              )}
            </div>
          </div>
          {rows.length === 0 && !loading && (
            <p className="py-8 text-center text-sm text-muted-foreground">
              没有匹配的格子。试试切换筛选条件、显示全不适用行，或换个搜索词。
            </p>
          )}
        </CardContent>
      </Card>

      <EndpointSheet
        row={endpointRow}
        vulns={allVulns}
        onClose={() => setEndpointKey(null)}
        taskId={taskId}
        onAudited={reload}
      />
      <CellSheet cell={cellSel} onClose={() => setCellSel(null)} taskId={taskId} onAudited={reload} />
    </div>
  );
}

function RowSummary({ r, onClick }: { r: RowData; onClick: () => void }) {
  const parts: { n: number; label: string; cls: string }[] = [
    { n: r.counts.confirmed ?? 0, label: "漏洞", cls: "text-red-600 dark:text-red-400" },
    { n: (r.counts.pending ?? 0) + (r.counts.dispatched ?? 0), label: "会派", cls: "text-blue-600 dark:text-blue-400" },
    { n: r.guard, label: "守卫", cls: "text-amber-600 dark:text-amber-400" },
    { n: r.low, label: "低置信", cls: "text-slate-500 dark:text-slate-400" },
    { n: r.counts.unverified ?? 0, label: "未验", cls: "text-slate-500 dark:text-slate-400" },
    { n: r.counts.needs_more ?? 0, label: "待定", cls: "text-violet-600 dark:text-violet-400" },
    { n: r.counts.clean ?? 0, label: "通过", cls: "text-emerald-600 dark:text-emerald-400" },
  ].filter((x) => x.n > 0);
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-full min-w-0 items-center justify-center gap-1 overflow-hidden px-1 text-[10px] hover:underline"
      title="查看该接口全部漏洞类型"
    >
      {parts.length === 0 ? (
        <span className="text-muted-foreground/50">—</span>
      ) : (
        parts.slice(0, 5).map((p) => (
          <span key={p.label} className={cn("whitespace-nowrap font-medium", p.cls)}>
            {p.label}
            {p.n > 1 ? p.n : ""}
          </span>
        ))
      )}
    </button>
  );
}

function SummaryRow({
  r,
  allVulns,
  onOpen,
}: {
  r: RowData;
  allVulns: VulnDef[];
  onOpen: () => void;
}) {
  const status = summaryStatus(r);
  const bucket = summaryBucket(r);
  const pending = (r.counts.pending ?? 0) + (r.counts.dispatched ?? 0);
  const chips = [
    { n: r.counts.confirmed ?? 0, label: "漏洞", cls: "text-red-600 dark:text-red-400" },
    { n: pending, label: "待审", cls: "text-blue-600 dark:text-blue-400" },
    { n: r.counts.clean ?? 0, label: "通过", cls: "text-emerald-600 dark:text-emerald-400" },
    { n: r.counts.unverified ?? 0, label: "未验", cls: "text-slate-500 dark:text-slate-400" },
  ].filter((x) => x.n > 0);

  return (
    <div
      className="grid items-center border-b border-border/60 px-2 hover:bg-muted/30"
      style={{ gridTemplateColumns: SUMMARY_GRID, height: SUMMARY_ROW_H }}
    >
      <button
        type="button"
        onClick={onOpen}
        className="flex min-w-0 items-center gap-2 text-left"
        title="查看该接口全部漏洞类型"
      >
        <Badge variant="outline" className="shrink-0 px-1 py-0 font-mono text-[9px]">
          {r.method}
        </Badge>
        <span className="truncate font-mono text-[11px]">{r.url}</span>
      </button>
      <span className={cn("text-center text-[11px] font-semibold", bucket.cls)}>{bucket.label}</span>
      <span className="flex justify-center">
        <span className={cn("rounded border px-1.5 py-0.5 text-[10px] font-medium", status.cls)}>
          {status.label}
        </span>
      </span>
      <div className="min-w-0">
        <div className="truncate text-[11px] leading-4" title={summaryText(r, allVulns)}>
          {summaryText(r, allVulns)}
        </div>
        {chips.length > 0 && (
          <div className="mt-0.5 flex flex-wrap gap-1.5 text-[10px]">
            {chips.map((x) => (
              <span key={x.label} className={cn("whitespace-nowrap font-medium", x.cls)}>
                {x.label}
                {x.n > 1 ? x.n : ""}
              </span>
            ))}
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={onOpen}
        className="h-7 rounded border px-2 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground"
      >
        查看
      </button>
    </div>
  );
}

function EndpointSheet({
  row,
  vulns,
  onClose,
  taskId,
  onAudited,
}: {
  row: RowData | null;
  vulns: VulnDef[];
  onClose: () => void;
  taskId: string;
  onAudited?: () => void;
}) {
  const [active, setActive] = React.useState<string | null>(null);
  const [addOpen, setAddOpen] = React.useState(false);
  const [addVuln, setAddVuln] = React.useState("");
  const [addText, setAddText] = React.useState("");
  const [addBusy, setAddBusy] = React.useState(false);
  const [addMsg, setAddMsg] = React.useState<{ ok: boolean; text: string } | null>(null);
  React.useEffect(() => {
    setActive(null);
    setAddOpen(false);
    setAddVuln("");
    setAddText("");
    setAddMsg(null);
  }, [row?.key]);
  if (!row) return null;
  const cell = active ? row.cells.get(active) ?? null : null;
  const first = row.cells.values().next().value as CaCell | undefined;
  const dispatchN = (row.counts.pending ?? 0) + (row.counts.dispatched ?? 0);
  const byState = (pick: (c: CaCell) => boolean) =>
    vulns.filter((v) => {
      const c = row.cells.get(v.key);
      return !!c && pick(c);
    }).map((v) => v.label);
  const groups: { label: string; items: string[]; cls: string }[] = [
    { label: "会派发", cls: "text-blue-600 dark:text-blue-400", items: byState((c) => c.status === "pending" || c.status === "dispatched") },
    { label: "有守卫", cls: "text-amber-600 dark:text-amber-400", items: byState((c) => c.status === "hold" && !(c.reason ?? "").includes("低置信")) },
    { label: "低置信", cls: "text-slate-500 dark:text-slate-400", items: byState((c) => c.status === "hold" && (c.reason ?? "").includes("低置信")) },
    { label: "未验证", cls: "text-slate-500 dark:text-slate-400", items: byState((c) => c.status === "unverified") },
    { label: "已确认", cls: "text-red-600 dark:text-red-400", items: byState((c) => c.status === "confirmed") },
    { label: "已排除", cls: "text-emerald-600 dark:text-emerald-400", items: byState((c) => c.status === "clean") },
  ].filter((g) => g.items.length > 0);

  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full! gap-0 p-0 sm:max-w-[620px]!">
        <SheetHeader className="border-b p-4 pr-12">
          <SheetTitle className="flex items-center gap-2 text-sm">
            <Badge variant="outline" className="font-mono">{row.method}</Badge>
            <code className="break-all font-mono text-xs">{row.url}</code>
          </SheetTitle>
          <SheetDescription className="text-[11px]">
            {first ? (
              <>
                共 {row.cells.size} 类 · 会派 {dispatchN} · 守卫 {row.guard} ·
                低置信 {row.low} · 漏洞 {row.counts.confirmed ?? 0}
                {first.direction ? ` · ${first.direction}` : ""}
              </>
            ) : (
              "该接口没有格子"
            )}
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-3 overflow-auto p-4">
          <ManualAddType
            row={row}
            vulns={vulns}
            taskId={taskId}
            open={addOpen}
            onOpenChange={setAddOpen}
            vuln={addVuln}
            onVulnChange={setAddVuln}
            text={addText}
            onTextChange={setAddText}
            busy={addBusy}
            onBusyChange={setAddBusy}
            msg={addMsg}
            onMsgChange={setAddMsg}
            onAudited={onAudited}
          />
          {groups.length > 0 && (
            <div className="space-y-1 rounded border bg-muted/30 p-2 text-[11px]">
              {groups.map((g) => (
                <div key={g.label} className="flex gap-2">
                  <span className={cn("w-14 shrink-0 font-medium", g.cls)}>{g.label}</span>
                  <span className="min-w-0 break-words">{g.items.join("、")}</span>
                </div>
              ))}
            </div>
          )}
          <div className="space-y-1.5">
            <div className="text-[11px] font-medium text-muted-foreground">该接口的 {vulns.length} 类判定</div>
            <div className="overflow-hidden rounded border">
              {vulns.map((v) => {
                const c = row.cells.get(v.key);
                const meta = metaFor(c);
                return (
                  <button
                    key={v.key}
                    type="button"
                    disabled={!c}
                    onClick={() => setActive(active === v.key ? null : v.key)}
                    className={cn(
                      "flex w-full items-start gap-2 border-b px-2 py-2 text-left text-[11px] last:border-b-0",
                      active === v.key ? "bg-muted/60" : "hover:bg-muted/40",
                      !c && "opacity-50",
                    )}
                  >
                    <span className="w-16 shrink-0 font-medium">{v.label}</span>
                    <span className={cn("shrink-0 rounded border px-1 text-[10px] font-medium", meta.cell)}>
                      {meta.label}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-muted-foreground">
                      {c?.verdict || c?.reason || meta.hint}
                    </span>
                    <span className="shrink-0 text-muted-foreground/70">
                      {c ? `P${c.priority}` : "—"}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {cell && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="text-[11px] font-medium text-muted-foreground">
                  {vulns.find((v) => v.key === active)?.label} · 详情
                </div>
                <button type="button" className="text-[11px] text-muted-foreground hover:text-foreground" onClick={onClose}>
                  关闭
                </button>
              </div>
              <CellBody c={cell} taskId={taskId} onAudited={onAudited} />
            </div>
          )}
          {!cell && (
            <p className="text-[11px] text-muted-foreground">点上面任意一行展开该格详情。</p>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function ManualAddType({
  row,
  vulns,
  taskId,
  open,
  onOpenChange,
  vuln,
  onVulnChange,
  text,
  onTextChange,
  busy,
  onBusyChange,
  msg,
  onMsgChange,
  onAudited,
}: {
  row: RowData;
  vulns: VulnDef[];
  taskId: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  vuln: string;
  onVulnChange: (v: string) => void;
  text: string;
  onTextChange: (v: string) => void;
  busy: boolean;
  onBusyChange: (v: boolean) => void;
  msg: { ok: boolean; text: string } | null;
  onMsgChange: (v: { ok: boolean; text: string } | null) => void;
  onAudited?: () => void;
}) {
  const input = vuln.trim();
  const hit = vulns.find((v) => v.key === input || v.label === input);
  const resolved = hit?.key ?? input;
  const exists = !!resolved && row.cells.has(resolved);

  const submit = async () => {
    if (busy || !resolved) return;
    onBusyChange(true);
    onMsgChange(null);
    try {
      const r = await api.caManualAddCell(taskId, row.method, row.url, resolved, text.trim());
      const suffix = r.paused
        ? "；任务当前暂停，恢复后执行"
        : r.queued
          ? "；任务排队中"
          : "；worker 会尽快领取";
      const carry = r.flow_count > 0 ? `，已带 ${r.flow_count} 个流程节点` : "，该接口暂无 flow 线索";
      onMsgChange({
        ok: true,
        text: `${r.added ? "已新建该类型并派发" : "已补充审计现有格子"}（intent #${r.intent_id}）${carry}${suffix}`,
      });
      onOpenChange(false);
      onVulnChange("");
      onTextChange("");
      onAudited?.();
    } catch (e) {
      onMsgChange({ ok: false, text: String((e as Error)?.message ?? e) });
    } finally {
      onBusyChange(false);
    }
  };

  return (
    <div className="rounded border p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-medium">人工添加漏洞类型</div>
          <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
            分析器没覆盖的偏门类型可以直接补。系统会带上该接口的 flow / file:line，
            但不复制其他漏洞类型的 sink 或结论。
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={() => onOpenChange(!open)}>
          {open ? "收起" : "添加类型"}
        </Button>
      </div>
      {open && (
        <div className="mt-3 space-y-2">
          <input
            list="ca-vuln-types"
            value={vuln}
            onChange={(e) => onVulnChange(e.target.value)}
            placeholder="选择或输入类型，例如 authz / 越权 / 自定义类型"
            className="w-full rounded border bg-background px-2 py-1.5 text-[11px]"
          />
          <datalist id="ca-vuln-types">
            {vulns.map((v) => (
              <option key={v.key} value={v.key} label={v.label} />
            ))}
          </datalist>
          <textarea
            value={text}
            onChange={(e) => onTextChange(e.target.value)}
            rows={3}
            maxLength={2000}
            placeholder="可选：说明你怀疑的偏门漏洞和入口，例如：关注 relayState 未校验导致 SSO 回调绕过……"
            className="w-full resize-y rounded border bg-background p-2 text-[11px] leading-5"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={submit} disabled={busy || !resolved}>
              {busy ? "提交中…" : "添加并审计"}
            </Button>
            <span className="text-[11px] text-muted-foreground">
              {resolved ? `类型 key：${resolved}` : "先填写类型"}
              {exists ? " · 已存在，将补充审计" : ""}
            </span>
          </div>
          {msg && (
            <p className={cn("text-[11px]", msg.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")}>
              {msg.text}
            </p>
          )}
        </div>
      )}
      {!open && msg && (
        <p className={cn("mt-2 text-[11px]", msg.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")}>
          {msg.text}
        </p>
      )}
    </div>
  );
}

function CellSheet({
  cell,
  onClose,
  taskId,
  onAudited,
}: {
  cell: CaCell | null;
  onClose: () => void;
  taskId: string;
  onAudited?: () => void;
}) {
  if (!cell) return null;
  const meta = metaFor(cell);
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full! gap-0 p-0 sm:max-w-[640px]!">
        <SheetHeader className="border-b p-4 pr-12">
          <SheetTitle className="flex flex-wrap items-center gap-2 text-sm">
            <code className="break-all font-mono text-xs">{cell.cell_key}</code>
            <span className={cn("rounded border px-1 text-[10px] font-medium", meta.cell)}>{meta.label}</span>
            <Badge variant="outline" className="text-[10px]">
              {cell.bucket || "—"} · P{cell.priority}
            </Badge>
            {cell.intent_id ? <Badge variant="outline" className="text-[10px]">intent #{cell.intent_id}</Badge> : null}
          </SheetTitle>
          <SheetDescription className="text-[11px]">{meta.hint}</SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-auto p-4">
          <CellBody c={cell} taskId={taskId} onAudited={onAudited} />
        </div>
      </SheetContent>
    </Sheet>
  );
}

function CellBody({ c, taskId, onAudited }: { c: CaCell; taskId: string; onAudited?: () => void }) {
  const Icon =
    c.status === "confirmed"
      ? BugIcon
      : c.status === "clean"
        ? CircleCheckIcon
        : c.status === "needs_more"
          ? CircleHelpIcon
          : c.status === "hold"
            ? ShieldCheckIcon
            : MinusIcon;
  return (
    <div className="grid gap-3 text-xs">
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <Icon className="size-3.5" />
        <span>{STATUS_META[c.status]?.hint}</span>
      </div>
      <Section title="方向">{c.direction || "—"}</Section>
      {c.reason && <Section title="判定依据 / 不适用原因">{c.reason}</Section>}
      {c.verdict && <Section title="结论">{c.verdict}</Section>}
      {c.evidence != null && <Section title="证据">{pretty(c.evidence)}</Section>}
      {c.checklist != null && (Array.isArray(c.checklist) ? c.checklist.length > 0 : true) && (
        <Section title="判定标准">
          <ol className="list-decimal pl-4">
            {(Array.isArray(c.checklist) ? c.checklist : []).map((x: string, i: number) => (
              <li key={i}>{x}</li>
            ))}
          </ol>
        </Section>
      )}
      {(() => {
        const h = (c.hints && typeof c.hints === "object" ? (c.hints as Record<string, any>) : null);
        const flow = (h?.flow as any[]) || [];
        const sites = (h?.sites as any[]) || [];
        const guards = (h?.guards_seen as any[]) || [];
        if (!flow.length && !sites.length && !guards.length) {
          return c.hints != null ? <Section title="线索">{pretty(c.hints)}</Section> : null;
        }
        return (
          <>
            {flow.length > 0 && (
              <Section title="结构流程（controller → service → dao）">
                <ol className="list-decimal space-y-0.5 pl-4">
                  {flow.slice(0, 16).map((x: any, i: number) => (
                    <li key={i}>
                      {x.kind === "dao" ? "DAO: " : ""}
                      {x.name || x.cls} @ {x.file}:{x.line}
                      {x.sql_kind ? ` [${x.sql_kind}]` : ""}
                    </li>
                  ))}
                </ol>
              </Section>
            )}
            {sites.length > 0 && (
              <Section title="sink / 资源访问">
                <ul className="list-disc space-y-1 pl-4">
                  {sites.slice(0, 10).map((x: any, i: number) => (
                    <li key={i}>
                      {x.api || x.method || x.kind} @ {x.file}:{x.line}
                      {x.raw_signals?.length ? <span className="text-red-600"> raw={x.raw_signals.join(",")}</span> : null}
                      {x.parameterized_signals?.length ? <span className="text-emerald-600"> param={x.parameterized_signals.join(",")}</span> : null}
                      {x.sql ? <div className="mt-1 opacity-80">{String(x.sql).slice(0, 400)}</div> : null}
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            {guards.length > 0 && (
              <Section title="守卫线索（仅供判断，不代表安全）">
                <ul className="list-disc space-y-1 pl-4">
                  {guards.slice(0, 10).map((x: any, i: number) => (
                    <li key={i}>
                      {x.text || x.kind} @ {x.file}:{x.line}
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            <details>
              <summary className="cursor-pointer text-[11px] text-muted-foreground">原始 hints</summary>
              <Section title="hints">{pretty(c.hints)}</Section>
            </details>
          </>
        );
      })()}
      {c.trace != null && Array.isArray(c.trace) && c.trace.length > 0 && (
        <Section title="不可达 trace">
          <ul className="list-disc pl-4 font-mono">
            {c.trace.slice(0, 12).map((x: string, i: number) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        </Section>
      )}
      {c.last_error && <Section title="最近错误">{c.last_error}</Section>}
      <ManualAudit cell={c} taskId={taskId} onAudited={onAudited} />
    </div>
  );
}

function ManualAudit({
  cell,
  taskId,
  onAudited,
}: {
  cell: CaCell;
  taskId: string;
  onAudited?: () => void;
}) {
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState<{ ok: boolean; text: string } | null>(null);
  const blocked = cell.status === "dispatched";

  const submit = async () => {
    if (busy || blocked) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.caManualAudit(taskId, cell.cell_key, text.trim());
      const suffix = r.paused
        ? "；任务当前暂停，恢复后执行"
        : r.queued
          ? "；任务排队中"
          : "；worker 会尽快领取";
      setMsg({ ok: true, text: `已加入审计队列（intent #${r.intent_id}）${suffix}` });
      onAudited?.();
    } catch (e) {
      setMsg({ ok: false, text: String((e as Error)?.message ?? e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded border p-3">
      <div className="mb-1 text-[11px] font-medium">人工介入 · 发起审计</div>
      <p className="mb-2 text-[11px] leading-5 text-muted-foreground">
        矩阵判定为不适用 / 有守卫 / 未验证时，也可以让 worker 按你的建议审这一格。
        {blocked ? " 当前格子已在审计队列中，不能重复发起。" : ""}
        {["confirmed", "clean", "needs_more"].includes(cell.status)
          ? " 重新审计会用新结论覆盖当前结论。"
          : ""}
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        maxLength={2000}
        placeholder="填写审计建议，例如：重点看 order by 拼接和 ${} 的位置；确认 tenantId 是否来自 token；关注越权读取同租户他人数据……"
        className="w-full resize-y rounded border bg-background p-2 text-[11px] leading-5"
      />
      <div className="mt-2 flex items-center gap-2">
        <Button size="sm" onClick={submit} disabled={busy || blocked}>
          {busy ? "提交中…" : "发起审计"}
        </Button>
        <span className="text-[11px] text-muted-foreground">{text.trim().length} / 2000</span>
      </div>
      {msg && (
        <p className={cn("mt-2 text-[11px]", msg.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")}>
          {msg.text}
        </p>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="mb-1 text-[11px] font-medium text-muted-foreground">{title}</div>
      <div className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-muted/40 p-2 font-mono text-[11px]">
        {children}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "blue" | "emerald" | "red" | "amber" | "muted";
}) {
  const color =
    tone === "red"
      ? "text-red-600 dark:text-red-400"
      : tone === "emerald"
        ? "text-emerald-600 dark:text-emerald-400"
        : tone === "amber"
          ? "text-amber-600 dark:text-amber-400"
          : tone === "blue"
            ? "text-blue-600 dark:text-blue-400"
            : tone === "muted"
              ? "text-muted-foreground"
              : "";
  return (
    <Card>
      <CardContent className="p-3">
        <div className={cn("text-2xl font-semibold tabular-nums", color)}>{value}</div>
        <div className="text-xs text-muted-foreground">{label}</div>
      </CardContent>
    </Card>
  );
}
