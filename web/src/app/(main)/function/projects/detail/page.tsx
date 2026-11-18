"use client";

import * as React from "react";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import {
  ArrowLeftIcon,
  CheckCircle2Icon,
  ExternalLinkIcon,
  GitBranchIcon,
  GitCommitHorizontalIcon,
  HistoryIcon,
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
import { api } from "@/lib/api";
import type { CodeProject, ProjectAuditRun } from "@/lib/types";

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

function DetailInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const id = Number(sp.get("id") ?? "");
  const [p, setP] = React.useState<CodeProject | null>(null);
  const [audits, setAudits] = React.useState<ProjectAuditRun[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [checking, setChecking] = React.useState(false);
  const [starting, setStarting] = React.useState(false);
  const [error, setError] = React.useState("");
  const pollRef = React.useRef<number | null>(null);

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
            <Button
              className="w-full justify-start"
              variant="outline"
              disabled
              title={!hasAudit ? "先完成一次全量审计" : "增量审计将在下一阶段接入"}
            >
              <HistoryIcon className="size-4" />
              发起增量审计
            </Button>
            {latestAudit && (
              <div className="rounded-lg border p-2 text-xs">
                <div className="text-muted-foreground flex items-center justify-between gap-2">
                  <span>最近运行 #{latestAudit.id}</span>
                  <Badge variant="outline">{latestAudit.status}</Badge>
                </div>
                <div className="mt-1 font-mono">target {shortCommit(latestAudit.target_commit)}</div>
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
