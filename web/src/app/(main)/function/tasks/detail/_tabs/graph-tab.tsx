"use client";

import * as React from "react";

import { Card, CardContent } from "@/components/ui/card";
import { ExplorationGraph } from "@/components/exploration-graph";
import { api } from "@/lib/api";
import type { Edge, TaskNode } from "@/lib/types";

type GraphMode = "vuln" | "full";

export function GraphTab({ taskId }: { taskId: string }) {
  const [nodes, setNodes] = React.useState<TaskNode[]>([]);
  const [edges, setEdges] = React.useState<Edge[]>([]);
  const [mode, setMode] = React.useState<GraphMode>("vuln");
  // 上一次图数据的签名:轮询拿到相同数据时跳过 setState,避免整图无谓重建(拖动时
  // 才不会被 20s 轮询打断而顿挫)。只取影响渲染的字段。
  const sigRef = React.useRef("");

  React.useEffect(() => {
    let cancelled = false;
    sigRef.current = ""; // 换任务/视图:强制下一次刷新
    const load = () => {
      api
        .explorationGraph(taskId, mode)
        .then((g) => {
          if (cancelled) return;
          const ns = g.nodes ?? [];
          const es = g.edges ?? [];
          const sig = JSON.stringify([
            ns.map((n) => [n.id, n.type, n.state, n.priority, n.payload]),
            es.map((e) => [e.src, e.dst, e.rel]),
          ]);
          if (sig === sigRef.current) return; // 无变化 → 不重建
          sigRef.current = sig;
          setNodes(ns);
          setEdges(es);
        })
        .catch(() => {
          /* keep last good data */
        });
    };
    load();
    const timer = setInterval(load, 20000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [taskId, mode]);

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">探索链路</span>
          <span>·</span>
          <span>{mode === "vuln" ? "仅显示已确认漏洞的上游链路" : "显示全部探索节点与边"}</span>
        </div>
        <div className="flex rounded-md border p-0.5 text-xs">
          <button
            type="button"
            onClick={() => setMode("vuln")}
            className={
              mode === "vuln"
                ? "rounded bg-primary/10 px-2.5 py-1 font-medium text-primary"
                : "rounded px-2.5 py-1 text-muted-foreground hover:text-foreground"
            }
          >
            漏洞链路
          </button>
          <button
            type="button"
            onClick={() => setMode("full")}
            className={
              mode === "full"
                ? "rounded bg-primary/10 px-2.5 py-1 font-medium text-primary"
                : "rounded px-2.5 py-1 text-muted-foreground hover:text-foreground"
            }
          >
            全量链路
          </button>
        </div>
      </div>
      <CardContent className="p-0">
        <ExplorationGraph
          nodes={nodes}
          edges={edges}
          className="h-[72vh]"
          emptyHint={mode === "vuln" ? "当前任务还没有已确认漏洞，暂无漏洞链路" : "暂无探索数据"}
        />
      </CardContent>
    </Card>
  );
}
