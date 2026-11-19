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
import { api } from "@/lib/api";
import type { ChangeFile, ChangePreview, CodeProject, ProjectAuditRun } from "@/lib/types";

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
        {(file.endpoints ?? []).length > 0 && (
          <div className="space-y-1 text-xs">
            <div className="font-medium">直接受影响接口</div>
            {(file.endpoints ?? []).map((ep, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2 font-mono">
                <Badge variant="outline">{ep.method}</Badge>
                <span>{ep.path}</span>
                <span className="text-muted-foreground">:{ep.line}</span>
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
  const [detailsOpen, setDetailsOpen] = React.useState(false);
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
          if (run.status === "ready" && run.task_id) {
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
  const auditBusy = starting || latestAudit?.status === "fetching";
  const targetCommit = preview?.target_commit || p.last_seen_commit;
  const reviewed = !!preview?.target_commit && p.last_reviewed_commit === preview.target_commit;
  const targetHasChanges = !!p.last_audited_commit && !!p.last_seen_commit && p.last_seen_commit !== p.last_audited_commit;
  const latestPrepared =
    latestAudit?.status === "prepared" &&
    (!preview || latestAudit.target_commit === preview.target_commit) &&
    (!p.last_seen_commit || latestAudit.target_commit === p.last_seen_commit)
      ? latestAudit
      : null;
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
  const activeEndpoints = activeScope?.endpoints ?? [];
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
          <Button variant="outline" onClick={check} disabled={checking}>
            {checking ? <Loader2Icon className="size-4 animate-spin" /> : <RefreshCwIcon className="size-4" />}
            检查更新
          </Button>
        </div>
      </div>

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

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <GitCommitHorizontalIcon className="size-4" />
              分支状态
            </CardTitle>
            <CardDescription>项目绑定仓库和分支；审计运行固定到该分支的具体 commit。</CardDescription>
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

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldCheckIcon className="size-4" />
              审计运行
            </CardTitle>
            <CardDescription>全量建立基线，增量只审计变更影响面。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button className="w-full justify-start" onClick={startFullAudit} disabled={auditBusy}>
              {auditBusy ? <Loader2Icon className="size-4 animate-spin" /> : <PlayIcon className="size-4" />}
              {latestAudit?.status === "fetching" ? "正在准备源码…" : "发起全量审计"}
            </Button>
            {latestAudit?.status === "ready" && latestAudit.task_id && (
              <Button className="w-full justify-start" variant="outline" asChild>
                <Link href={`/function/tasks/detail?id=${latestAudit.task_id}`}>
                  <CheckCircle2Icon className="size-4" />
                  查看最近审计任务
                </Link>
              </Button>
            )}
            {latestAudit && (
              <div className="rounded-lg border p-2 text-xs">
                <div className="text-muted-foreground flex items-center justify-between gap-2">
                  <span>最近运行 #{latestAudit.id}</span>
                  <Badge variant="outline">{latestAudit.status}</Badge>
                </div>
                <div className="mt-1 font-mono">target {shortCommit(latestAudit.target_commit)}</div>
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
            <p className="text-muted-foreground text-xs leading-relaxed">
              全量审计会下载当前分支（{trackedBranch}）commit 的源码、创建任务并自动开跑；固定 commit 便于回溯。
            </p>
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
                  <Button size="sm" onClick={prepareIncremental} disabled={preparingIncremental || !!latestPrepared}>
                    {preparingIncremental ? <Loader2Icon className="size-4 animate-spin" /> : <ShieldCheckIcon className="size-4" />}
                    {latestPrepared ? "增量已准备" : "准备增量审计"}
                  </Button>
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

                  {activeEndpoints.length > 0 && (
                    <div className="space-y-2">
                      <div className="text-sm font-medium">直接受影响接口</div>
                      <div className="flex flex-wrap gap-2">
                        {activeEndpoints.map((ep, i) => (
                          <Badge key={`${ep.method}:${ep.path}:${i}`} variant="outline" className="font-mono">
                            {ep.method} {ep.path}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

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
