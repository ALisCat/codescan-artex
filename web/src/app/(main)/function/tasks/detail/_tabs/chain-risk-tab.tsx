"use client";

import * as React from "react";

import { useRouter } from "next/navigation";

import { GitBranchIcon, Loader2Icon, PlayIcon, RefreshCwIcon, TriangleAlertIcon } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { TaskNode } from "@/lib/types";

type ChainPayload = {
  kind?: string;
  chain?: boolean;
  summary?: string;
  detail?: string;
  evidence?: string;
  confidence?: string;
};

const ENDPOINT_RE = /\b(GET|POST|PUT|PATCH|DELETE)\s+(\/[^\s，。；;)\]]+)/gi;
const FINDING_REF_RE = /\bfinding\s*#(\d+)/gi;

function parsePayload(node: TaskNode): ChainPayload {
  try {
    const parsed = JSON.parse(node.payload ?? "{}");
    return parsed && typeof parsed === "object" ? (parsed as ChainPayload) : {};
  } catch {
    return {};
  }
}

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function extractEndpoints(text: string): string[] {
  const out: string[] = [];
  for (const match of text.matchAll(ENDPOINT_RE)) {
    out.push(`${match[1].toUpperCase()} ${match[2]}`);
  }
  return unique(out);
}

function extractFindingRefs(text: string): string[] {
  const out: string[] = [];
  for (const match of text.matchAll(FINDING_REF_RE)) {
    out.push(`#${match[1]}`);
  }
  return unique(out);
}

function fmtTime(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN");
}

export function ChainRiskTab({ taskId }: { taskId: string }) {
  const router = useRouter();
  const [observations, setObservations] = React.useState<TaskNode[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [auditing, setAuditing] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setLoading(true);
    api
      .chainObservations(taskId)
      .then((rows) => {
        setObservations(rows);
        setError("");
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [taskId]);

  React.useEffect(() => {
    load();
  }, [load]);

  const startAudit = React.useCallback(
    async (ids: string[]) => {
      if (ids.length === 0 || auditing) return;
      setAuditing(ids.length === 1 ? ids[0] : "all");
      try {
        const result = await api.auditChainObservations(taskId, ids);
        toast.success(
          result.count === 1
            ? "链式风险审计任务已创建"
            : `已创建包含 ${result.count} 项链式风险的审计任务`,
        );
        router.push(`/function/tasks/detail?id=${result.task_id}`);
      } catch (e) {
        toast.error("开启链式风险审计失败：" + (e as Error).message);
      } finally {
        setAuditing(null);
      }
    },
    [auditing, router, taskId],
  );

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader className="gap-2">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle className="flex items-center gap-2 text-sm">
                <GitBranchIcon className="size-4" />
                链式风险 / 延后观察
                {loading && <Loader2Icon className="size-3.5 animate-spin text-muted-foreground" />}
              </CardTitle>
              <CardDescription className="max-w-3xl text-xs leading-5">
                这里展示 worker 留档的跨接口、跨格子组合风险。它不参与矩阵覆盖，不会自动补派或重新打开已完成矩阵；
                后续需要人工确认是否创建跟进任务或合并到已有 finding。
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                onClick={() => void startAudit(observations.map((item) => item.id))}
                disabled={loading || observations.length === 0 || auditing !== null}
              >
                {auditing === "all" ? <Loader2Icon className="size-4 animate-spin" /> : <PlayIcon className="size-4" />}
                一键审计全部
              </Button>
              <Button size="sm" variant="outline" onClick={load} disabled={loading || auditing !== null}>
                {loading ? <Loader2Icon className="size-4 animate-spin" /> : <RefreshCwIcon className="size-4" />}
                刷新
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {error && <p className="text-xs text-destructive">读取链式风险失败：{error}</p>}
          {!loading && observations.length === 0 && (
            <div className="text-muted-foreground rounded-lg border border-dashed p-8 text-center text-sm">
              暂无链式风险观察。
            </div>
          )}
          {observations.map((node) => {
            const payload = parsePayload(node);
            const summary = payload.summary || node.payload || "（无摘要）";
            const detail = payload.detail || "";
            const text = `${summary}\n${detail}`;
            const endpoints = extractEndpoints(text);
            const findingRefs = extractFindingRefs(text);
            return (
              <div key={node.id} className="rounded-lg border bg-background/60 p-3">
                <div className="mb-2 flex flex-wrap items-center gap-1.5">
                  <Badge variant="outline" className="gap-1 border-amber-500/40 text-amber-700 dark:text-amber-300">
                    <TriangleAlertIcon className="size-3" />
                    延后观察
                  </Badge>
                  <code className="bg-muted rounded px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                    #{node.id}
                  </code>
                  {payload.confidence && <Badge variant="secondary">{payload.confidence}</Badge>}
                  <span className="text-muted-foreground text-[11px]">{node.origin || "worker"}</span>
                  <span className="text-muted-foreground text-[11px]">{fmtTime(node.ts)}</span>
                  <Button
                    size="sm"
                    variant="outline"
                    className="ml-auto h-7"
                    disabled={auditing !== null}
                    onClick={() => void startAudit([node.id])}
                  >
                    {auditing === node.id ? (
                      <Loader2Icon className="size-3.5 animate-spin" />
                    ) : (
                      <PlayIcon className="size-3.5" />
                    )}
                    开启审计
                  </Button>
                </div>
                <p className="text-sm leading-5 font-medium">{summary}</p>
                {endpoints.length > 0 && (
                  <div className="mt-2 flex flex-wrap items-center gap-1">
                    <span className="text-muted-foreground text-[11px]">涉及接口</span>
                    {endpoints.map((endpoint) => (
                      <Badge key={endpoint} variant="outline" className="font-mono text-[10px]">
                        {endpoint}
                      </Badge>
                    ))}
                  </div>
                )}
                {findingRefs.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap items-center gap-1">
                    <span className="text-muted-foreground text-[11px]">关联 finding</span>
                    {findingRefs.map((ref) => (
                      <Badge key={ref} variant="secondary" className="text-[10px]">
                        {ref}
                      </Badge>
                    ))}
                  </div>
                )}
                {detail && (
                  <details className="mt-2">
                    <summary className="text-muted-foreground cursor-pointer text-xs hover:text-foreground">
                      查看完整线索与证据
                    </summary>
                    <pre className="mt-2 max-h-72 overflow-auto rounded-md border bg-muted/30 p-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
                      {detail}
                      {payload.evidence ? `\n\nEvidence:\n${payload.evidence}` : ""}
                    </pre>
                  </details>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
