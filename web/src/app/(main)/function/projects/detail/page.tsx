"use client";

import * as React from "react";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import {
  ArrowLeftIcon,
  CheckCircle2Icon,
  ChevronDownIcon,
  ChevronUpIcon,
  ExternalLinkIcon,
  FileCode2Icon,
  GitBranchIcon,
  GitCommitHorizontalIcon,
  Loader2Icon,
  PlayIcon,
  RefreshCwIcon,
  ShieldCheckIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import type {
  ChangeFile,
  ChangePreview,
  CodeProject,
  IncrementalGapCell,
  ManualCellSpec,
  ProjectAccessProfile,
  ProjectAuditRun,
} from "@/lib/types";

function fmtTime(v?: string) {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function shortCommit(v: string) {
  return v ? v.slice(0, 12) : "—";
}
const DEFAULT_ACCESS_PROFILE: ProjectAccessProfile = {
  mode: "simple",
  multi_end: "unknown",
  management_scope: "unknown",
  management_internal_scope: "unknown",
  client_scope: "unknown",
  shared_management: "unknown",
  notes: "",
};
const ADVANCED_ACCESS_TEMPLATE = JSON.stringify(
  {
    roles: {
      ADMIN: {
        resource: {
          read: "all",
          list: "all",
        },
      },
      CLIENT: {
        resource: {
          read: "self",
        },
      },
    },
    endpoints: [
      {
        match: "GET /api/admin/resource/{id}",
        resource: "resource",
        action: "read",
        roles: ["ADMIN"],
      },
      {
        match: "GET /api/client/resource/{id}",
        resource: "resource",
        action: "read",
        roles: ["CLIENT"],
      },
    ],
  },
  null,
  2,
);


function accessScopeLabel(v: string) {
  switch (v) {
    case "all":
      return "查看全部数据";
    case "department":
      return "按部门/科室";
    case "assigned":
      return "按分配/归属";
    case "self":
      return "仅本人";
    case "related":
      return "本人及关联";
    case "public":
      return "公开/共享";
    default:
      return "不确定";
  }
}

function accessChoiceLabel(v: string) {
  if (v === "yes") return "是";
  if (v === "no") return "否";
  return "不确定";
}

const VULN_LABELS: Record<string, string> = {
  authz: "越权",
  authn: "认证/回调",
  "business-logic": "业务逻辑",
  "business_logic": "业务逻辑",
  "command-exec": "命令/表达式",
  csrf: "CSRF",
  deserialization: "反序列化",
  "file-upload": "文件上传",
  "ldap-injection": "LDAP",
  "ldap_injection": "LDAP",
  "mass-assignment": "批量赋值",
  "mass_assignment": "批量赋值",
  "open-redirect": "开放重定向",
  "open_redirect": "开放重定向",
  "path-traversal": "路径穿越",
  "race-condition": "竞态",
  "race_condition": "竞态",
  "sql-injection": "SQL 注入",
  "sql_injection": "SQL 注入",
  ssrf: "SSRF",
  ssti: "SSTI",
  xss: "XSS",
  xxe: "XXE",
  secrets: "硬编码凭据",
  crypto: "弱加密",
  dependency: "依赖漏洞",
  "sensitive-data": "敏感数据",
  "sensitive_data": "敏感数据",
};

function vulnLabel(v: string) {
  return VULN_LABELS[v] ?? v;
}

function changeStatusLabel(s: string) {
  switch (s) {
    case "added":
      return "新增";
    case "deleted":
      return "删除";
    case "renamed":
      return "重命名";
    default:
      return "修改";
  }
}

function changeStatusClass(s: string) {
  switch (s) {
    case "added":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
    case "deleted":
      return "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300";
    case "renamed":
      return "border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300";
    default:
      return "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }
}

function ChangeFileRow({ file }: { file: ChangeFile }) {
  return (
    <details className="group rounded-lg border">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
        <Badge variant="outline" className={changeStatusClass(file.status)}>
          {changeStatusLabel(file.status)}
        </Badge>
        <span className="min-w-0 flex-1 truncate font-mono text-xs">{file.path}</span>
        <span className="text-emerald-600 dark:text-emerald-400">+{file.additions}</span>
        <span className="text-red-600 dark:text-red-400">-{file.deletions}</span>
        <span className="text-muted-foreground text-xs group-open:hidden">展开</span>
      </summary>
      <div className="space-y-3 border-t px-3 py-3">
        {(file.hunks ?? []).length > 0 && (
          <div className="space-y-1 text-xs">
            <div className="font-medium">变更块</div>
            {(file.hunks ?? []).map((h, i) => (
              <div key={i} className="text-muted-foreground font-mono">
                旧 {h.old_start}-{h.old_start + h.old_lines - 1} → 新 {h.new_start}-
                {h.new_start + h.new_lines - 1}
              </div>
            ))}
          </div>
        )}
        {file.diff ? (
          <pre className="bg-muted/40 max-h-96 overflow-auto rounded-md border p-3 text-xs leading-relaxed">
            {file.diff}
          </pre>
        ) : (
          <div className="text-muted-foreground text-xs">
            {file.diff_omitted ? "diff 过大，已省略；请到 GitLab 查看完整变更。" : "GitLab 未返回该文件的文本 diff。"}
          </div>
        )}
      </div>
    </details>
  );
}

function DetailInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const id = Number(sp.get("id") ?? "");
  const [p, setP] = React.useState<CodeProject | null>(null);
  const [audits, setAudits] = React.useState<ProjectAuditRun[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [checking, setChecking] = React.useState(false);
  const [starting, setStarting] = React.useState(false);
  const [preparingIncremental, setPreparingIncremental] = React.useState(false);
  const [startingIncremental, setStartingIncremental] = React.useState(false);
  const [gapCells, setGapCells] = React.useState<IncrementalGapCell[]>([]);
  const [manualSelections, setManualSelections] = React.useState<Record<string, string>>({});
  const [rejectedRiskKeys, setRejectedRiskKeys] = React.useState<Set<string>>(new Set());
  const [newApplicableCells, setNewApplicableCells] = React.useState<IncrementalGapCell[]>([]);
  const [selectedNewKeys, setSelectedNewKeys] = React.useState<Set<string>>(new Set());
  const [detailsOpen, setDetailsOpen] = React.useState(false);
  const [runsOpen, setRunsOpen] = React.useState(false);
  const [accessOpen, setAccessOpen] = React.useState(false);
  const [accessSaving, setAccessSaving] = React.useState(false);
  const [accessForm, setAccessForm] = React.useState<ProjectAccessProfile>(DEFAULT_ACCESS_PROFILE);
  const [accessAdvancedJSON, setAccessAdvancedJSON] = React.useState("{}");
  const [incrementalTab, setIncrementalTab] = React.useState<"unreviewed" | "reviewed">("unreviewed");
  const [reviewDialogOpen, setReviewDialogOpen] = React.useState(false);
  const [preview, setPreview] = React.useState<ChangePreview | null>(null);
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [previewError, setPreviewError] = React.useState("");
  const [reviewNote, setReviewNote] = React.useState("");
  const [reviewing, setReviewing] = React.useState(false);
  const [error, setError] = React.useState("");
  const pollRef = React.useRef<number | null>(null);
  const autoPreviewRef = React.useRef(false);

  const load = React.useCallback(() => {
    if (!Number.isFinite(id) || id <= 0) {
      setError("项目 ID 不合法");
      setLoading(false);
      return;
    }
    setLoading(true);
    Promise.all([api.project(id), api.projectAudits(id).catch(() => [])])
      .then(([x, runs]) => {
        setP(x);
        setAudits(runs);
        setError("");
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [id]);

  React.useEffect(() => {
    load();
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [load]);

  async function startFullAudit() {
    if (!p) return;
    setStarting(true);
    try {
      const res = await api.startProjectAudit(p.id, "full");
      setAudits((prev) => [res.audit, ...prev.filter((r) => r.id !== res.audit.id)]);
      toast.success("已开始拉取源码，准备全量审计任务…");
      const runID = res.audit.id;
      const deadline = Date.now() + 30 * 60 * 1000;
      const tick = async () => {
        try {
          const run = await api.projectAudit(p.id, runID);
          setAudits((prev) => [run, ...prev.filter((r) => r.id !== run.id)]);
          if ((run.status === "ready" || run.status === "running") && run.task_id) {
            if (pollRef.current) window.clearInterval(pollRef.current);
            pollRef.current = null;
            toast.success("全量审计任务已创建");
            router.push(`/function/tasks/detail?id=${run.task_id}`);
          } else if (run.status === "failed") {
            if (pollRef.current) window.clearInterval(pollRef.current);
            pollRef.current = null;
            toast.error("全量审计失败：" + (run.error_message || "未知错误"));
            load();
          } else if (Date.now() > deadline) {
            if (pollRef.current) window.clearInterval(pollRef.current);
            pollRef.current = null;
            toast.error("源码准备超时，请到任务列表或刷新项目查看结果");
          }
        } catch {
          // A transient poll failure should not stop the run; the next tick retries.
        }
      };
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = window.setInterval(() => void tick(), 2500);
    } catch (e) {
      toast.error("发起全量审计失败：" + (e as Error).message);
    } finally {
      setStarting(false);
    }
  }

  async function loadPreview() {
    if (!p) return;
    setPreviewLoading(true);
    setPreviewError("");
    try {
      const r = await api.projectChangePreview(p.id);
      setPreview(r);
      const unread = r.unreviewed?.summary.commits ?? 0;
      const reviewed = r.reviewed?.summary.commits ?? 0;
      setIncrementalTab(unread === 0 && reviewed > 0 ? "reviewed" : "unreviewed");
      if (r.error) setPreviewError(r.error);
    } catch (e) {
      setPreviewError((e as Error).message);
    } finally {
      setPreviewLoading(false);
    }
  }

  React.useEffect(() => {
    if (!p || preview || previewLoading || previewError || autoPreviewRef.current) return;
    if (!p.last_audited_commit || !p.last_seen_commit || p.last_seen_commit === p.last_audited_commit) return;
    autoPreviewRef.current = true;
    void loadPreview();
  }, [p, preview, previewLoading, previewError]);

  async function markReviewed() {
    if (!p || !preview?.target_commit) {
      toast.error("请先预览变更");
      return;
    }
    setReviewing(true);
    try {
      const next = await api.reviewProject(p.id, preview.target_commit, reviewNote.trim());
      setP(next);
      setReviewNote("");
      setReviewDialogOpen(false);
      toast.success("已标记已阅；审计基线未改变");
      await loadPreview();
    } catch (e) {
      toast.error("标记已阅失败：" + (e as Error).message);
    } finally {
      setReviewing(false);
    }
  }

  async function prepareIncremental() {
    if (!p) return;
    setPreparingIncremental(true);
    try {
      const run = await api.prepareIncrementalAudit(p.id);
      setAudits((prev) => [run, ...prev.filter((r) => r.id !== run.id)]);
      toast.success("已开始准备增量源码和矩阵…");
      const runID = run.id;
      const deadline = Date.now() + 20 * 60 * 1000;
      const tick = async () => {
        try {
          const next = await api.projectAudit(p.id, runID);
          setAudits((prev) => [next, ...prev.filter((r) => r.id !== next.id)]);
          if (next.status === "prepared") {
            if (pollRef.current) window.clearInterval(pollRef.current);
            pollRef.current = null;
            toast.success(`增量准备完成：${next.changed_files} 个文件，${next.delta_cells} 个 delta 格`);
            load();
          } else if (next.status === "failed") {
            if (pollRef.current) window.clearInterval(pollRef.current);
            pollRef.current = null;
            toast.error("增量准备失败：" + (next.error_message || "未知错误"));
            load();
          } else if (Date.now() > deadline) {
            if (pollRef.current) window.clearInterval(pollRef.current);
            pollRef.current = null;
            toast.error("增量准备超时，请刷新项目查看结果");
          }
        } catch {
          // transient poll error: next tick retries
        }
      };
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = window.setInterval(() => void tick(), 2000);
    } catch (e) {
      toast.error("启动增量准备失败：" + (e as Error).message);
    } finally {
      setPreparingIncremental(false);
    }
  }

  async function startIncremental() {
    if (!p || !preparedRun) return;
    setStartingIncremental(true);
    try {
      const manualCells: ManualCellSpec[] = Object.entries(manualSelections).flatMap(([label, raw]) => {
        const value = raw.trim();
        if (!value) return [];
        const parts = label.split(" ");
        const method = parts.shift() ?? "";
        const url = parts.join(" ");
        const group = gapCells.filter((cell) => `${cell.method} ${cell.url}` === label);
        const known = group.find(
          (cell) =>
            cell.vulnclass.toLowerCase() === value.toLowerCase() ||
            vulnLabel(cell.vulnclass).toLowerCase() === value.toLowerCase(),
        );
        return [{ method, url, vulnclass: known?.vulnclass ?? value }];
      });
      const res = await api.startIncrementalAudit(
        p.id,
        preparedRun.id,
        manualCells,
        [...rejectedRiskKeys],
        [...selectedNewKeys],
      );
      setAudits((prev) => [res.audit, ...prev.filter((r) => r.id !== res.audit.id)]);
      toast.success("增量审计任务已创建");
      router.push(`/function/tasks/detail?id=${res.task_id}`);
    } catch (e) {
      toast.error("启动增量审计失败：" + (e as Error).message);
    } finally {
      setStartingIncremental(false);
    }
  }

  async function check() {
    if (!p) return;
    setChecking(true);
    try {
      const next = await api.checkProject(p.id);
      setP(next);
      toast.success(next.last_check_error ? "检查失败：" + next.last_check_error : "已检查项目分支 HEAD");
    } catch (e) {
      toast.error("检查失败：" + (e as Error).message);
    } finally {
      setChecking(false);
    }
  }

  function openAccessProfile() {
    if (!p) return;
    const next = { ...DEFAULT_ACCESS_PROFILE, ...(p.access_profile ?? {}) };
    setAccessForm(next);
    setAccessAdvancedJSON(
      next.mode === "advanced" && next.advanced && Object.keys(next.advanced).length > 0
        ? JSON.stringify(next.advanced, null, 2)
        : ADVANCED_ACCESS_TEMPLATE,
    );
    setAccessOpen(true);
  }

  async function saveAccessProfile() {
    if (!p) return;
    let payload = accessForm;
    if (accessForm.mode === "advanced") {
      try {
        const parsed = JSON.parse(accessAdvancedJSON);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          toast.error("精细规则必须填写 JSON 对象");
          return;
        }
        payload = { ...accessForm, advanced: parsed as Record<string, unknown> };
      } catch {
        toast.error("精细规则不是合法 JSON");
        return;
      }
    }
    setAccessSaving(true);
    try {
      const profile = await api.updateProjectAccessProfile(p.id, payload);
      setP({ ...p, access_profile: profile });
      setAccessOpen(false);
      toast.success("访问模型已保存；后续任务将使用该业务参考");
    } catch (e) {
      toast.error("保存访问模型失败：" + (e as Error).message);
    } finally {
      setAccessSaving(false);
    }
  }

  const preparedRun = audits[0]?.status === "prepared" ? audits[0] : null;
  const affectedEndpoints = new Set<string>(preparedRun?.delta_gaps ?? []);
  const autoRiskEndpoints = new Set<string>();
  const autoRiskByEndpoint = new Map<string, { cellKey: string; vulnclass: string }[]>();
  for (const key of preparedRun?.delta_cell_keys ?? []) {
    const i = key.lastIndexOf(":");
    if (i > 0) {
      const url = key.slice(0, i);
      const vuln = key.slice(i + 1);
      affectedEndpoints.add(url);
      autoRiskEndpoints.add(url);
      const types = autoRiskByEndpoint.get(url) ?? [];
      if (!types.some((item) => item.cellKey === key)) types.push({ cellKey: key, vulnclass: vuln });
      autoRiskByEndpoint.set(url, types);
    }
  }
  const autoRiskRows = [...autoRiskByEndpoint.entries()]
    .map(([url, cells]) => ({ url, cells: cells.filter((cell) => !rejectedRiskKeys.has(cell.cellKey)) }))
    .filter((row) => row.cells.length > 0);
  const newApplicableByEndpoint = new Map<string, IncrementalGapCell[]>();
  for (const cell of newApplicableCells) {
    const label = `${cell.method} ${cell.url}`;
    const cells = newApplicableByEndpoint.get(label) ?? [];
    cells.push(cell);
    newApplicableByEndpoint.set(label, cells);
  }
  const newApplicableRows = [...newApplicableByEndpoint.entries()].map(([label, cells]) => ({
    label,
    method: cells[0]?.method ?? "",
    url: cells[0]?.url ?? "",
    cells,
  }));
  const manualSelected = Object.values(manualSelections).some((value) => value.trim() !== "");
  const remainingDeltaKeys = (preparedRun?.delta_cell_keys ?? []).filter((key) => !rejectedRiskKeys.has(key));
  const canStartIncremental =
    !!preparedRun &&
    (remainingDeltaKeys.length > 0 || manualSelected || selectedNewKeys.size > 0);

  React.useEffect(() => {
    if (!p || !preparedRun || preparedRun.delta_gaps.length === 0) {
      setGapCells([]);
      setManualSelections({});
      setRejectedRiskKeys(new Set());
      return;
    }
    let alive = true;
    api
      .projectGapCells(p.id, preparedRun.id)
      .then((res) => {
        if (alive) {
          setGapCells(res.cells);
          setManualSelections({});
          setRejectedRiskKeys(new Set());
        }
      })
      .catch(() => {
        if (alive) setGapCells([]);
      });
    return () => {
      alive = false;
    };
  }, [p, preparedRun]);

  React.useEffect(() => {
    if (!p || !preparedRun) {
      setNewApplicableCells([]);
      setSelectedNewKeys(new Set());
      return;
    }
    let alive = true;
    api
      .projectNewApplicableCells(p.id, preparedRun.id)
      .then((res) => {
        if (alive) {
          setNewApplicableCells(res.cells);
          setSelectedNewKeys(new Set());
        }
      })
      .catch(() => {
        if (alive) setNewApplicableCells([]);
      });
    return () => {
      alive = false;
    };
  }, [p, preparedRun]);

  if (loading) {
    return (
      <div className="text-muted-foreground flex flex-1 items-center justify-center gap-2 py-24 text-sm">
        <Loader2Icon className="size-4 animate-spin" />
        正在读取项目…
      </div>
    );
  }
  if (error || !p) {
    return (
      <div className="flex flex-1 flex-col items-center gap-4 py-24">
        <TriangleAlertIcon className="size-8 text-amber-500" />
        <div className="font-medium">{error || "项目不存在"}</div>
        <Button variant="outline" asChild>
          <Link href="/function/projects">
            <ArrowLeftIcon className="size-4" />
            返回项目
          </Link>
        </Button>
      </div>
    );
  }

  const updateAvailable = !!p.last_audited_commit && !!p.last_seen_commit && p.last_seen_commit !== p.last_audited_commit;
  const hasAudit = !!p.last_audited_commit;
  const trackedBranch = p.tracked_branch || p.default_branch || "main";
  const latestAudit = audits[0];
  const activeAudit = audits.find((run) =>
    ["fetching", "preparing", "running", "ready", "review"].includes(run.status),
  );
  const activeFullAudit = activeAudit?.mode === "full" ? activeAudit : null;
  const fullAuditBusy = starting || !!activeFullAudit;
  const fullAuditDisabled = starting || !!activeAudit;
  const targetCommit = preview?.target_commit || p.last_seen_commit;
  const reviewed = !!preview?.target_commit && p.last_reviewed_commit === preview.target_commit;
  const targetHasChanges = !!p.last_audited_commit && !!p.last_seen_commit && p.last_seen_commit !== p.last_audited_commit;
  const latestPrepared =
    latestAudit?.status === "prepared" &&
    (!preview || latestAudit.target_commit === preview.target_commit) &&
    (!p.last_seen_commit || latestAudit.target_commit === p.last_seen_commit)
      ? latestAudit
      : null;
  const runChain = [...audits].slice(0, 12).reverse();
  const activeScope = incrementalTab === "reviewed" ? preview?.reviewed : preview?.unreviewed;
  const unreadCount = preview?.unreviewed?.summary.commits ?? preview?.review_summary?.commits ?? 0;
  const reviewedCount =
    preview?.reviewed?.summary.commits ?? Math.max(0, (preview?.audit_gap.commits ?? 0) - unreadCount);
  const emptySummary = { commits: 0, files_changed: 0, additions: 0, deletions: 0 };
  const activeSummary =
    activeScope?.summary ??
    (incrementalTab === "unreviewed" ? preview?.review_summary : emptySummary) ??
    emptySummary;
  const activeCommits =
    activeScope?.commits ?? (incrementalTab === "unreviewed" ? preview?.review_commits ?? [] : []);
  const activeFiles = activeScope?.files ?? [];
  const activeWarnings = activeScope?.warnings ?? [];
  const activeBase = activeScope?.base_commit || (incrementalTab === "unreviewed" ? preview?.review_base_commit : preview?.base_commit);
  const activeTarget = activeScope?.target_commit || preview?.target_commit;
  const incrementalState = !p.last_audited_commit
    ? { label: "需要全量基线", tone: "warning" }
    : previewLoading
      ? { label: "检查中", tone: "muted" }
      : preview?.no_changes || (!preview && !targetHasChanges)
        ? { label: "无新提交", tone: "ok" }
        : latestPrepared
          ? { label: "增量已准备", tone: "ok" }
          : preview
            ? unreadCount > 0
              ? { label: reviewedCount > 0 ? "待处理" : "有新变更", tone: "warning" }
              : reviewedCount > 0
                ? { label: "已阅，未审计", tone: "warning" }
                : reviewed
                  ? { label: "本次已标记已阅", tone: "ok" }
                  : { label: "待决定", tone: "warning" }
            : { label: "有新提交", tone: "warning" };
  const stateClass =
    incrementalState.tone === "ok"
      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
      : incrementalState.tone === "warning"
        ? "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300"
        : "text-muted-foreground";

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <Button variant="ghost" size="sm" className="-ml-2" asChild>
            <Link href="/function/projects">
              <ArrowLeftIcon className="size-4" />
              项目
            </Link>
          </Button>
          <h1 className="text-xl font-semibold tracking-tight">{p.name}</h1>
          <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-xs">
            <span>{p.path}</span>
            <span className="inline-flex items-center gap-1">
              <GitBranchIcon className="size-3.5" />
              {trackedBranch}
            </span>
            {p.web_url && (
              <a href={p.web_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:underline">
                <ExternalLinkIcon className="size-3.5" />
                GitLab
              </a>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={startFullAudit} disabled={fullAuditDisabled}>
            {fullAuditBusy ? <Loader2Icon className="size-4 animate-spin" /> : <PlayIcon className="size-4" />}
            {starting
              ? "正在发起…"
              : activeFullAudit
                ? "全量审计进行中…"
                : activeAudit
                  ? "已有审计进行中"
                  : "发起全量审计"}
          </Button>
          <Button variant="outline" onClick={openAccessProfile}>
            <ShieldCheckIcon className="size-4" />
            访问模型
          </Button>
          <Button variant="outline" onClick={() => setRunsOpen(true)}>
            <GitCommitHorizontalIcon className="size-4" />
            审计记录
          </Button>
          <Button variant="outline" onClick={check} disabled={checking}>
            {checking ? <Loader2Icon className="size-4 animate-spin" /> : <RefreshCwIcon className="size-4" />}
            检查更新
          </Button>
        </div>
      </div>

      {activeFullAudit && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-sky-500/30 bg-sky-500/5 px-3 py-2 text-sm">
          <div className="flex min-w-0 items-start gap-2">
            <Loader2Icon className="mt-0.5 size-4 shrink-0 animate-spin text-sky-600" />
            <div className="min-w-0">
              <div className="font-medium text-sky-800 dark:text-sky-200">全量审计已发起</div>
              <div className="text-muted-foreground mt-0.5 text-xs">
                审计批次 #{activeFullAudit.batch_no ?? activeFullAudit.id} ·
                {activeFullAudit.status === "fetching"
                  ? " 正在下载源码"
                  : activeFullAudit.status === "preparing"
                    ? " 正在准备矩阵"
                    : activeFullAudit.status === "running"
                      ? " 任务已创建，审计进行中"
                      : activeFullAudit.status === "ready"
                        ? " 任务已就绪"
                        : " 等待当前任务结束"}
                {activeFullAudit.task_id && (
                  <>
                    {" · "}
                    <Link
                      href={`/function/tasks/detail?id=${activeFullAudit.task_id}`}
                      className="text-foreground underline underline-offset-2"
                    >
                      执行任务 #{activeFullAudit.task_id}
                    </Link>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="text-muted-foreground shrink-0 font-mono text-[11px]">target {shortCommit(activeFullAudit.target_commit)}</div>
        </div>
      )}

      {p.last_check_error && (
        <Card className="border-red-500/30 bg-red-500/5">
          <CardContent className="flex items-start gap-3 py-4 text-sm">
            <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-red-600" />
            <div>
              <div className="font-medium text-red-700 dark:text-red-300">上次检查失败</div>
              <div className="text-muted-foreground mt-0.5">{p.last_check_error}</div>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CheckCircle2Icon className="size-4" />
            项目信息
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-5">
          <div>
            <div className="text-muted-foreground text-xs">GitLab 项目 ID</div>
            <div className="mt-1 font-mono">{p.gitlab_project_id || "—"}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-xs">目标分支</div>
            <div className="mt-1 inline-flex items-center gap-1">
              <GitBranchIcon className="size-3.5" />
              {trackedBranch}
            </div>
          </div>
          <div>
            <div className="text-muted-foreground text-xs">状态</div>
            <div className="mt-1">{p.status || "active"}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-xs">添加时间</div>
            <div className="mt-1">{fmtTime(p.created_at)}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-xs">最近更新</div>
            <div className="mt-1">{fmtTime(p.updated_at)}</div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <GitCommitHorizontalIcon className="size-4" />
              分支状态
            </CardTitle>
            <CardDescription>项目绑定仓库和分支；每次审计批次固定到该分支的具体 commit。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border p-3">
                <div className="text-muted-foreground text-xs">目标分支 HEAD</div>
                <div className="mt-1 font-mono text-sm">{shortCommit(p.last_seen_commit)}</div>
                <div className="text-muted-foreground mt-1 text-xs">检查于 {fmtTime(p.last_checked_at)}</div>
              </div>
              <div className="rounded-lg border p-3">
                <div className="text-muted-foreground text-xs">最近成功审计</div>
                <div className="mt-1 font-mono text-sm">{shortCommit(p.last_audited_commit)}</div>
                <div className="text-muted-foreground mt-1 text-xs">
                  {hasAudit ? "增量审计将以此为基线" : "还没有成功审计基线"}
                </div>
                {p.last_audited_task_id && (
                  <div className="text-muted-foreground mt-1 text-xs">
                    基线任务{" "}
                    <Link
                      href={`/function/tasks/detail?id=${p.last_audited_task_id}`}
                      className="text-foreground underline underline-offset-2"
                    >
                      #{p.last_audited_task_id}
                    </Link>
                  </div>
                )}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Badge
                variant="outline"
                className={
                  updateAvailable
                    ? "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300"
                    : "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                }
              >
                {updateAvailable ? "目标分支有新提交" : hasAudit ? "基线是最新" : "等待首次审计"}
              </Badge>
              {p.last_seen_commit && <span className="text-muted-foreground text-xs">target {shortCommit(p.last_seen_commit)}</span>}
            </div>
          </CardContent>
        </Card>

      </div>

      <Card>
        <CardHeader className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <FileCode2Icon className="size-4" />
                增量分析
              </CardTitle>
              <Badge variant="outline" className={stateClass}>
                {incrementalState.label}
              </Badge>
            </div>
            <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
              <span>审计基线 <code className="font-mono text-foreground">{shortCommit(p.last_audited_commit)}</code></span>
              <span>已阅 <code className="font-mono text-foreground">{shortCommit(p.last_reviewed_commit)}</code></span>
              <span>目标 <code className="font-mono text-foreground">{shortCommit(targetCommit)}</code></span>
            </div>
          </div>
          <Button variant={preview ? "outline" : "default"} size="sm" onClick={loadPreview} disabled={previewLoading || !hasAudit}>
            {previewLoading ? <Loader2Icon className="size-4 animate-spin" /> : <RefreshCwIcon className="size-4" />}
            {preview ? "重新预览" : "查看变更"}
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {previewError && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-700 dark:text-red-300">
              {previewError}
            </div>
          )}

          {preparedRun && (
            <div className="rounded-lg border border-sky-500/30 bg-sky-500/5 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">增量审计已准备</span>
                  <Badge variant="outline" className="border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300">
                    审计批次 #{preparedRun.batch_no ?? preparedRun.id}
                  </Badge>
                </div>
                <Button
                  size="sm"
                  onClick={startIncremental}
                  disabled={startingIncremental || !canStartIncremental}
                >
                  {startingIncremental ? <Loader2Icon className="size-4 animate-spin" /> : <PlayIcon className="size-4" />}
                  {canStartIncremental ? "开始增量审计" : "请选择审计范围"}
                </Button>
              </div>
              <div className="text-muted-foreground mt-2 font-mono text-xs">
                {shortCommit(preparedRun.base_commit)} → {shortCommit(preparedRun.target_commit)}
              </div>
              <div className="text-muted-foreground mt-1 text-xs">
                {preparedRun.changed_files} 个变更文件 · 影响接口 {affectedEndpoints.size} 个，自动分析发现{" "}
                {autoRiskEndpoints.size} 个接口可能存在风险，已录入矩阵；未变更格从基线任务只读继承。
                {(preparedRun.new_applicable_cell_keys?.length ?? 0) > 0 &&
                  ` 另有 ${preparedRun.new_applicable_cell_keys.length} 个新增适用格待人工确认。`}
              </div>
              {rejectedRiskKeys.size > 0 && (
                <div className="text-muted-foreground mt-1 flex items-center gap-1 text-xs">
                  已否定 {rejectedRiskKeys.size} 项自动分析结果
                  <button
                    type="button"
                    className="text-foreground underline underline-offset-2"
                    onClick={() => setRejectedRiskKeys(new Set())}
                  >
                    恢复
                  </button>
                </div>
              )}

              <div className={`mt-3 grid gap-3 ${autoRiskRows.length > 0 && (preparedRun.delta_gaps?.length ?? 0) > 0 ? "lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]" : ""}`}>
                {autoRiskRows.length > 0 && (
                  <div className="overflow-hidden rounded-md border bg-background/60">
                    <div className="border-b px-3 py-2 text-xs font-medium">增量分析 · 自动发现的风险类型</div>
                    <table className="w-full text-left text-[11px]">
                      <thead className="text-muted-foreground border-b">
                        <tr>
                          <th className="px-3 py-1.5 font-medium">接口</th>
                          <th className="px-3 py-1.5 font-medium">自动发现的风险类型</th>
                        </tr>
                      </thead>
                      <tbody>
                        {autoRiskRows.map((row) => (
                          <tr key={row.url} className="border-b last:border-b-0">
                            <td className="max-w-64 truncate px-3 py-1.5 font-mono" title={row.url}>
                              {row.url}
                            </td>
                            <td className="px-3 py-1.5">
                              <div className="flex flex-wrap gap-1">
                                {row.cells.map((cell) => (
                                  <Badge key={cell.cellKey} variant="outline" className="gap-1 pr-1 font-normal">
                                    {vulnLabel(cell.vulnclass)}
                                    <button
                                      type="button"
                                      className="text-muted-foreground hover:text-foreground rounded px-0.5"
                                      aria-label={`否定 ${vulnLabel(cell.vulnclass)}`}
                                      title="否定该自动分析结果，不纳入本次审计"
                                      onClick={() => setRejectedRiskKeys((prev) => new Set(prev).add(cell.cellKey))}
                                    >
                                      ×
                                    </button>
                                  </Badge>
                                ))}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {(preparedRun.delta_gaps?.length ?? 0) > 0 && (
                  <div className="overflow-hidden rounded-md border bg-background/60">
                    <div className="border-b px-3 py-2 text-xs font-medium">新增/变更接口 · 人工指定审计类型</div>
                    <div className="space-y-1.5 p-2">
                      <div className="text-muted-foreground px-1 pb-1 text-[11px]">
                        这些接口当前矩阵全部 N/A；选择或输入类型后，点击「开始增量审计」会把对应格加入任务。
                      </div>
                      {gapCells.length === 0 ? (
                        <div className="text-muted-foreground p-1 font-mono text-[11px]">
                          {preparedRun.delta_gaps.join("、")}
                        </div>
                      ) : (
                        Object.entries(
                          gapCells.reduce<Record<string, { method: string; url: string; cells: IncrementalGapCell[] }>>((acc, cell) => {
                            const key = `${cell.method} ${cell.url}`;
                            if (!acc[key]) acc[key] = { method: cell.method, url: cell.url, cells: [] };
                            acc[key].cells.push(cell);
                            return acc;
                          }, {}),
                        ).map(([label, group]) => (
                          <div key={label} className="flex flex-wrap items-center justify-between gap-2 rounded border bg-background/60 px-2 py-1.5">
                            <span className="min-w-0 break-all font-mono text-[11px]">
                              <span className="mr-1 font-sans text-muted-foreground">{group.method}</span>
                              {group.url}
                            </span>
                            <>
                              <input
                                list={`vuln-options-${label.replace(/[^a-zA-Z0-9_-]/g, "_")}`}
                                className="h-7 w-48 rounded border bg-background px-2 text-xs"
                                placeholder="选择或输入漏洞类型"
                                value={manualSelections[label] ?? ""}
                                onChange={(e) =>
                                  setManualSelections((prev) => ({ ...prev, [label]: e.target.value }))
                                }
                              />
                              <datalist id={`vuln-options-${label.replace(/[^a-zA-Z0-9_-]/g, "_")}`}>
                                {group.cells.map((cell) => (
                                  <option key={cell.cell_key} value={vulnLabel(cell.vulnclass)} />
                                ))}
                              </datalist>
                            </>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </div>

              {newApplicableRows.length > 0 && (
                <div className="mt-3 overflow-hidden rounded-md border border-amber-500/30 bg-background/60">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-500/20 px-3 py-2">
                    <div className="text-xs font-medium">
                      新增适用格 · 人工确认
                      <span className="text-muted-foreground ml-2 font-normal">
                        已选 {selectedNewKeys.size} / {newApplicableCells.length}
                      </span>
                    </div>
                    <div className="flex gap-1">
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-6 px-2 text-[11px]"
                        onClick={() => setSelectedNewKeys(new Set(newApplicableCells.map((cell) => cell.cell_key)))}
                      >
                        全选
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-6 px-2 text-[11px]"
                        onClick={() => setSelectedNewKeys(new Set())}
                      >
                        清空
                      </Button>
                    </div>
                  </div>
                  <div className="text-muted-foreground border-b border-border/60 px-3 py-1.5 text-[11px]">
                    分析器认为可能适用，但没有命中本次变更行。默认不审计；勾选后纳入本次审计。
                  </div>
                  <div className="space-y-1.5 p-2">
                    {newApplicableRows.map((row) => (
                      <div
                        key={row.label}
                        className="flex flex-wrap items-center justify-between gap-2 rounded border bg-background/60 px-2 py-1.5"
                      >
                        <span className="min-w-0 break-all font-mono text-[11px]">
                          <span className="mr-1 font-sans text-muted-foreground">{row.method}</span>
                          {row.url}
                        </span>
                        <div className="flex flex-wrap gap-1">
                          {row.cells.map((cell) => {
                            const checked = selectedNewKeys.has(cell.cell_key);
                            return (
                              <label
                                key={cell.cell_key}
                                className={`inline-flex cursor-pointer items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] ${
                                  checked
                                    ? "border-amber-500/50 bg-amber-500/10 text-amber-800 dark:text-amber-200"
                                    : "border-border bg-background/60 text-muted-foreground"
                                }`}
                              >
                                <input
                                  type="checkbox"
                                  className="size-3 accent-amber-600"
                                  checked={checked}
                                  onChange={() => {
                                    setSelectedNewKeys((prev) => {
                                      const next = new Set(prev);
                                      if (next.has(cell.cell_key)) next.delete(cell.cell_key);
                                      else next.add(cell.cell_key);
                                      return next;
                                    });
                                  }}
                                />
                                {vulnLabel(cell.vulnclass)}
                              </label>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {preparedRun.base_task_id && (
                <div className="text-muted-foreground mt-2 text-xs">
                  基线任务{" "}
                  <Link href={`/function/tasks/detail?id=${preparedRun.base_task_id}`} className="text-foreground underline underline-offset-2">
                    #{preparedRun.base_task_id}
                  </Link>
                </div>
              )}
              {preparedRun.target_commit !== p.last_seen_commit && (
                <div className="mt-1 text-xs text-amber-700 dark:text-amber-300">
                  该准备固定到旧 target；当前 HEAD 已更新，新提交会留给下一次增量。
                </div>
              )}
            </div>
          )}

          {!preview && !previewLoading && !previewError && (
            <div className="text-muted-foreground flex items-center gap-2 text-sm">
              <GitCommitHorizontalIcon className="size-4" />
              {hasAudit
                ? targetHasChanges
                  ? "目标分支有新提交，点击「查看变更」确认影响范围。"
                  : "当前目标分支与审计基线一致，没有新提交。"
                : "还没有成功审计基线，请先完成一次全量审计。"}
            </div>
          )}

          {preview?.needs_full && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-700 dark:text-amber-300">
              还没有成功审计基线，无法做增量预览。请先完成一次全量审计。
            </div>
          )}

          {preview?.no_changes && (
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm text-emerald-700 dark:text-emerald-300">
              目标分支没有新提交，无需增量分析。
            </div>
          )}

          {preview && !preview.needs_full && !preview.no_changes && (
            <>
              <div className="bg-muted/20 flex flex-col gap-2 rounded-lg border p-1.5 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-wrap gap-1">
                  <Button
                    type="button"
                    size="sm"
                    variant={incrementalTab === "unreviewed" ? "secondary" : "ghost"}
                    onClick={() => {
                      setIncrementalTab("unreviewed");
                      setDetailsOpen(false);
                    }}
                  >
                    未阅
                    <Badge variant="outline" className="tabular-nums">
                      {unreadCount}
                    </Badge>
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant={incrementalTab === "reviewed" ? "secondary" : "ghost"}
                    onClick={() => {
                      setIncrementalTab("reviewed");
                      setDetailsOpen(false);
                    }}
                  >
                    已阅未审计
                    <Badge variant="outline" className="tabular-nums">
                      {reviewedCount}
                    </Badge>
                  </Button>
                </div>
                {activeBase && activeTarget && (
                  <span className="text-muted-foreground px-2 font-mono text-xs">
                    范围 {shortCommit(activeBase)} → {shortCommit(activeTarget)}
                  </span>
                )}
              </div>

              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <div className="rounded-lg border p-3">
                  <div className="text-muted-foreground text-xs">提交</div>
                  <div className="mt-1 text-2xl font-semibold tabular-nums">{activeSummary.commits}</div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-muted-foreground text-xs">文件</div>
                  <div className="mt-1 text-2xl font-semibold tabular-nums">{activeSummary.files_changed}</div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-muted-foreground text-xs">新增行</div>
                  <div className="mt-1 text-2xl font-semibold text-emerald-600 tabular-nums dark:text-emerald-400">
                    +{activeSummary.additions}
                  </div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-muted-foreground text-xs">删除行</div>
                  <div className="mt-1 text-2xl font-semibold text-red-600 tabular-nums dark:text-red-400">
                    -{activeSummary.deletions}
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300">
                  审计缺口：{preview.audit_gap.commits} 个提交 / {preview.audit_gap.files_changed} 个文件
                </Badge>
                {latestPrepared && (
                  <Badge variant="outline" className="border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300">
                    增量源码已准备
                  </Badge>
                )}
              </div>

              <div className="flex flex-col gap-3 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="text-sm font-medium">
                    {activeSummary.commits === 0
                      ? incrementalTab === "reviewed"
                        ? "没有已阅未审计变更"
                        : "没有未阅变更"
                      : incrementalTab === "reviewed"
                        ? "这些变更已阅，但还没有审计"
                        : "这次新变更怎么处理？"}
                  </div>
                  <div className="text-muted-foreground text-xs">
                    {activeSummary.commits === 0
                      ? incrementalTab === "reviewed"
                        ? "新变更标记已阅后会保留在这里，直到完成增量审计。"
                        : "已阅但未审计的变更在「已阅未审计」模块。"
                      : incrementalTab === "reviewed"
                        ? unreadCount > 0
                          ? "准备增量审计会同时覆盖未阅和已阅未审计变更。"
                          : "已阅不会改变审计基线；增量审计会覆盖这些代码。"
                        : "标记已阅只会移入「已阅未审计」，审计基线保持不变。"}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Tooltip delayDuration={150}>
                    <TooltipTrigger asChild>
                      <Button size="sm" onClick={prepareIncremental} disabled={preparingIncremental || !!latestPrepared}>
                        {preparingIncremental ? <Loader2Icon className="size-4 animate-spin" /> : <ShieldCheckIcon className="size-4" />}
                        {latestPrepared ? "增量已准备" : "准备增量审计"}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-sm">
                      <div className="space-y-1">
                        <div className="font-medium">会审计全部未审计提交</div>
                        <div>
                          本次从审计基线审计到目标 HEAD，包含已阅未审计 {reviewedCount} 个提交、未阅 {unreadCount} 个提交。
                        </div>
                        <div>审计基线必须连续推进，不能跳过中间未审计的提交。</div>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                  {incrementalTab === "unreviewed" && unreadCount > 0 && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setReviewDialogOpen(true)}
                      disabled={reviewing || reviewed}
                    >
                      <CheckCircle2Icon className="size-4" />
                      {reviewed ? "已标记已阅" : "本次无需审计"}
                    </Button>
                  )}
                </div>
              </div>

              <Button variant="ghost" size="sm" className="-ml-2" onClick={() => setDetailsOpen((v) => !v)}>
                {detailsOpen ? <ChevronUpIcon className="size-4" /> : <ChevronDownIcon className="size-4" />}
                {detailsOpen ? "收起当前模块详情" : "查看当前模块的文件、提交和接口详情"}
              </Button>

              {detailsOpen && (
                <div className="space-y-4 border-t pt-4">
                  {activeCommits.length > 0 && (
                    <div className="space-y-2">
                      <div className="text-sm font-medium">提交列表</div>
                      <div className="space-y-1 rounded-lg border">
                        {activeCommits.slice(0, 20).map((c) => (
                          <div key={c.id} className="flex flex-wrap items-center gap-2 border-b px-3 py-2 text-xs last:border-b-0">
                            <span className="text-muted-foreground font-mono">{shortCommit(c.id || c.short_id || "")}</span>
                            <span className="min-w-0 flex-1 truncate">{c.title}</span>
                            <span className="text-muted-foreground">{c.author_name || ""}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="space-y-2">
                    <div className="text-sm font-medium">变更文件（点击展开 diff）</div>
                    {activeFiles.length === 0 ? (
                      <div className="text-muted-foreground text-sm">当前模块没有文件变更。</div>
                    ) : (
                      <div className="space-y-2">
                        {activeFiles.map((f) => (
                          <ChangeFileRow key={`${activeScope?.base_commit}:${f.old_path}:${f.new_path}`} file={f} />
                        ))}
                      </div>
                    )}
                  </div>


                  {Array.from(new Set([...activeWarnings, ...preview.warnings])).length > 0 && (
                    <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-700 dark:text-amber-300">
                      {Array.from(new Set([...activeWarnings, ...preview.warnings])).map((w, i) => (
                        <div key={i}>{w}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <Sheet open={runsOpen} onOpenChange={setRunsOpen}>
        <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 data-[side=right]:sm:max-w-lg">
          <SheetHeader className="border-b px-4 py-3">
            <SheetTitle className="flex items-center gap-2">
              <GitCommitHorizontalIcon className="size-4" />
              审计记录
            </SheetTitle>
            <SheetDescription>
              每次发起全量或增量审计会生成一条审计批次记录，并创建一个执行任务。
              审计批次编号与任务编号不同。
            </SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
            <div className="rounded-md border bg-muted/20 px-3 py-2 text-[11px] text-muted-foreground">
              <div><span className="font-medium text-foreground">审计批次</span>：一次审计发起记录。</div>
              <div><span className="font-medium text-foreground">执行任务</span>：真正运行审计的 Agent 任务。</div>
            </div>
            <div className="rounded-lg border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-sm font-medium">发起全量审计</div>
                  <div className="text-muted-foreground mt-0.5 text-xs">
                    下载当前分支 {trackedBranch} 的源码并建立完整矩阵基线。
                  </div>
                </div>
                <Button size="sm" onClick={startFullAudit} disabled={fullAuditDisabled}>
                  {fullAuditBusy ? <Loader2Icon className="size-4 animate-spin" /> : <PlayIcon className="size-4" />}
                  {starting
                    ? "正在发起…"
                    : activeFullAudit
                      ? "全量审计进行中…"
                      : activeAudit
                        ? "已有审计进行中"
                        : "发起全量审计"}
                </Button>
              </div>
              {latestAudit?.task_id && ["ready", "review", "running"].includes(latestAudit.status) && (
                <Button className="mt-3 w-full justify-start" variant="outline" asChild>
                  <Link href={`/function/tasks/detail?id=${latestAudit.task_id}`}>
                    <CheckCircle2Icon className="size-4" />
                    {latestAudit.mode === "manual_review" ? "打开人工复核任务" : "查看最近审计任务"}
                  </Link>
                </Button>
              )}
              {latestAudit && (
                <div className="text-muted-foreground mt-3 rounded-md border px-2 py-1.5 text-[11px]">
                  <div className="flex items-center justify-between gap-2">
                    <span>最近审计批次 #{latestAudit.batch_no ?? latestAudit.id}</span>
                    <Badge variant="outline">{latestAudit.status}</Badge>
                  </div>
                  <div className="mt-1 font-mono">target {shortCommit(latestAudit.target_commit)}</div>
                  {latestAudit.mode === "manual_review" && <div className="mt-1">人工复核 · 不推进审计基线</div>}
                  {latestAudit.status === "prepared" && (
                    <div className="mt-1">
                      变更文件 {latestAudit.changed_files} · delta 格 {latestAudit.delta_cells}
                    </div>
                  )}
                  {latestAudit.error_message && (
                    <div className="mt-1 text-red-600 dark:text-red-400">{latestAudit.error_message}</div>
                  )}
                </div>
              )}
            </div>

            <div>
              <div className="mb-2 text-sm font-medium">运行记录</div>
              {runChain.length === 0 ? (
                <div className="text-muted-foreground text-sm">还没有审计记录。</div>
              ) : (
                <div className="space-y-0">
                  {runChain.map((run, index) => {
                    const isCurrentBaseline = p.last_audited_run_id === run.id && p.last_audited_commit === run.target_commit;
                    const isLatest = latestAudit?.id === run.id;
                    const label = run.mode === "full" ? "全量" : run.mode === "manual_review" ? "人工复核" : "增量";
                    return (
                      <div key={run.id} className="relative flex gap-3 pb-4 last:pb-0">
                        <div className="relative flex w-4 shrink-0 justify-center">
                          {index < runChain.length - 1 && <span className="bg-border absolute top-4 bottom-0 w-px" />}
                          <span
                            className={
                              isCurrentBaseline
                                ? "relative z-10 mt-1 size-2.5 rounded-full bg-emerald-500 ring-4 ring-emerald-500/15"
                                : isLatest
                                  ? "relative z-10 mt-1 size-2.5 rounded-full bg-sky-500 ring-4 ring-sky-500/15"
                                  : "bg-muted-foreground/40 relative z-10 mt-1 size-2.5 rounded-full ring-4 ring-muted"
                            }
                          />
                        </div>
                        <div className="min-w-0 flex-1 rounded-lg border px-3 py-2">
                          <div className="flex flex-wrap items-center gap-2 text-xs">
                            <Badge variant="outline">{label}</Badge>
                            <span className="font-medium">审计批次 #{run.batch_no ?? run.id}</span>
                            <span className="text-muted-foreground font-mono">
                              {shortCommit(run.base_commit)} → {shortCommit(run.target_commit)}
                            </span>
                            <Badge variant="outline">{run.status}</Badge>
                            {isCurrentBaseline && (
                              <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">
                                当前基线
                              </Badge>
                            )}
                            {isLatest && !isCurrentBaseline && (
                              <Badge variant="outline" className="border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300">
                                最近运行
                              </Badge>
                            )}
                            {run.task_id && (
                              <Link
                                href={`/function/tasks/detail?id=${run.task_id}`}
                                className="text-foreground inline-flex items-center gap-0.5 underline underline-offset-2"
                              >
                                执行任务 #{run.task_id}
                              </Link>
                            )}
                          </div>
                          <div className="text-muted-foreground mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px]">
                            {run.mode === "incremental" && (
                              <>
                                <span>变更文件 {run.changed_files}</span>
                                <span>自动 delta {run.delta_cells}</span>
                                {(run.delta_gaps?.length ?? 0) > 0 && <span>未覆盖接口 {run.delta_gaps.length}</span>}
                              </>
                            )}
                            {run.mode === "manual_review" && <span>不推进审计基线</span>}
                            {run.mode === "full" && <span>建立完整矩阵基线</span>}
                            <span>创建于 {fmtTime(run.created_at)}</span>
                          </div>
                          {run.error_message && <div className="mt-1 text-[11px] text-red-600 dark:text-red-400">{run.error_message}</div>}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </SheetContent>
      </Sheet>

      <Dialog open={accessOpen} onOpenChange={setAccessOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>项目访问模型</DialogTitle>
            <DialogDescription>
              只回答业务层面的访问范围，不需要填写代码里的角色名或接口路径。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>配置模式</Label>
              <select
                className="h-8 w-full rounded border bg-background px-2 text-sm"
                value={accessForm.mode}
                onChange={(e) => {
                  const mode = e.target.value as ProjectAccessProfile["mode"];
                  setAccessForm({ ...accessForm, mode });
                  if (mode === "advanced" && accessAdvancedJSON.trim() === "{}") {
                    setAccessAdvancedJSON(ADVANCED_ACCESS_TEMPLATE);
                  }
                }}
              >
                <option value="simple">简单模式：只回答业务问题</option>
                <option value="advanced">精细模式：填写角色、资源和范围规则</option>
              </select>
            </div>
            {accessForm.mode === "simple" ? (
              <>
            <div className="space-y-1.5">
              <Label>本项目是否包含多个端？</Label>
              <select
                className="h-8 w-full rounded border bg-background px-2 text-sm"
                value={accessForm.multi_end}
                onChange={(e) => setAccessForm({ ...accessForm, multi_end: e.target.value as ProjectAccessProfile["multi_end"] })}
              >
                <option value="yes">是</option>
                <option value="no">否</option>
                <option value="unknown">不确定</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>管理端用户可以查看的业务数据范围（患者/客户/订单等）</Label>
              <div className="text-muted-foreground text-[11px]">
                这里的管理端范围默认描述普通管理端用户；admin/超级管理员默认可访问全部数据。
              </div>
              <select
                className="h-8 w-full rounded border bg-background px-2 text-sm"
                value={accessForm.management_scope}
                onChange={(e) => setAccessForm({ ...accessForm, management_scope: e.target.value as ProjectAccessProfile["management_scope"] })}
              >
                <option value="all">全部业务数据（包含部门、分配和本人数据）</option>
                <option value="department">本组织/部门业务数据（包含本人数据）</option>
                <option value="assigned">分配给自己的业务数据（包含本人数据）</option>
                <option value="self">仅本人业务数据</option>
                <option value="unknown">不确定</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>管理端用户可以查看的内部资料范围</Label>
              <select
                className="h-8 w-full rounded border bg-background px-2 text-sm"
                value={accessForm.management_internal_scope}
                onChange={(e) =>
                  setAccessForm({
                    ...accessForm,
                    management_internal_scope: e.target.value as ProjectAccessProfile["management_internal_scope"],
                  })
                }
              >
                <option value="all">全部成员资料（包含本部门和本人资料）</option>
                <option value="department">本组织/部门成员资料（包含本人资料）</option>
                <option value="self">仅本人资料</option>
                <option value="unknown">不确定</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>客户端私有数据范围</Label>
              <select
                className="h-8 w-full rounded border bg-background px-2 text-sm"
                value={accessForm.client_scope}
                onChange={(e) => setAccessForm({ ...accessForm, client_scope: e.target.value as ProjectAccessProfile["client_scope"] })}
              >
                <option value="related">本人及关联数据（包含本人数据）</option>
                <option value="self">仅本人数据</option>
                <option value="unknown">不确定</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>是否存在客户端可以访问的管理端接口？</Label>
              <select
                className="h-8 w-full rounded border bg-background px-2 text-sm"
                value={accessForm.shared_management}
                onChange={(e) => setAccessForm({ ...accessForm, shared_management: e.target.value as ProjectAccessProfile["shared_management"] })}
              >
                <option value="no">没有</option>
                <option value="yes">有</option>
                <option value="unknown">不确定</option>
              </select>
            </div>
              </>
            ) : (
              <div className="space-y-1.5">
                <Label htmlFor="access-advanced">精细规则 JSON</Label>
                <div className="text-muted-foreground text-[11px]">
                  以下仅是结构示例，需要按实际角色、资源、接口和数据范围修改。
                </div>
                <textarea
                  id="access-advanced"
                  className="min-h-64 w-full rounded border bg-background p-2 font-mono text-xs"
                  value={accessAdvancedJSON}
                  onChange={(e) => setAccessAdvancedJSON(e.target.value)}
                  spellCheck={false}
                />
                <div className="text-muted-foreground text-[11px]">
                  填写角色、资源、操作和数据范围规则。未覆盖的接口会由 worker 返回 needs_more。
                </div>
                <details className="overflow-hidden rounded-md border bg-muted/20 px-3 py-2 text-xs">
                  <summary className="cursor-pointer font-medium">字段说明与可选值</summary>
                  <div className="text-muted-foreground mt-2 space-y-2">
                    <p><code>roles</code>：角色名到资源规则的映射。角色名必须和代码中的权限角色一致，例如 <code>ADMIN</code>、<code>CLIENT</code>。</p>
                    <p><code>resource</code>：资源标识，例如 <code>resource</code>、<code>patient</code>、<code>order</code>。</p>
                    <p><code>read / list / create / update / delete / export / approve / assign</code>：对资源执行的操作。模板中的 <code>read</code> 表示查看单条资源，<code>list</code> 表示查看列表；其他操作按名称理解。</p>
                    <p><code>scope</code>：数据范围，可选 <code>all</code>（全部）、<code>department</code>（部门/科室）、<code>assigned</code>（分配给当前主体）、<code>self</code>（本人）、<code>public</code>（公开/共享）、<code>unknown</code>（不确定）。</p>
                    <p><code>endpoints[].match</code>：HTTP 方法和路径，例如 <code>GET /api/admin/resource/{id}</code>。</p>
                    <p><code>endpoints[].resource / action / roles</code>：接口对应的资源、操作和角色；用于明确接口属于哪条规则。</p>
                    <p>未出现在规则中的角色、资源、操作或接口，worker 应返回 <code>needs_more</code>，不能自行猜测业务允许。</p>
                  </div>
                </details>
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="access-notes">业务补充说明（可选）</Label>
              <Input
                id="access-notes"
                value={accessForm.notes}
                onChange={(e) => setAccessForm({ ...accessForm, notes: e.target.value })}
                placeholder="例如：共享排班接口允许客户端访问"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAccessOpen(false)} disabled={accessSaving}>
              取消
            </Button>
            <Button onClick={() => void saveAccessProfile()} disabled={accessSaving}>
              {accessSaving && <Loader2Icon className="size-4 animate-spin" />}
              保存访问模型
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={reviewDialogOpen} onOpenChange={setReviewDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>本次不审计？</DialogTitle>
            <DialogDescription>
              只把这次变更标记为已阅，不改变审计基线，也不会产生 finding。后续真正审计时仍会覆盖这段代码。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="review-note">已阅说明（可选）</Label>
            <Input
              id="review-note"
              value={reviewNote}
              onChange={(e) => setReviewNote(e.target.value)}
              placeholder="例如：仅测试代码、暂缓审计"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !reviewing) void markReviewed();
              }}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReviewDialogOpen(false)}>
              取消
            </Button>
            <Button onClick={() => void markReviewed()} disabled={reviewing}>
              {reviewing && <Loader2Icon className="size-4 animate-spin" />}
              确认已阅
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>



    </div>
  );
}

export default function ProjectDetailPage() {
  return (
    <React.Suspense fallback={null}>
      <DetailInner />
    </React.Suspense>
  );
}
