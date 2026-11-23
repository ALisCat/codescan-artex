"use client";

import * as React from "react";

import Link from "next/link";

import {
  AlertTriangleIcon,
  ArrowRightIcon,
  CheckCircle2Icon,
  ExternalLinkIcon,
  FolderGit2Icon,
  GitBranchIcon,
  Loader2Icon,
  PlusIcon,
  RefreshCwIcon,
  SearchIcon,
  Settings2Icon,
  Trash2Icon,
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import type { CodeProject, GitLabBranch, GitLabProject, Settings } from "@/lib/types";

function shortCommit(c: string) {
  return c ? c.slice(0, 8) : "—";
}

function projectState(p: CodeProject) {
  if (p.last_check_error) return { label: "检查失败", tone: "danger" as const };
  if (!p.last_audited_commit) return { label: "未审计", tone: "muted" as const };
  if (p.last_seen_commit && p.last_seen_commit !== p.last_audited_commit) {
    return { label: "有更新", tone: "warning" as const };
  }
  return { label: "已审计", tone: "ok" as const };
}

function StateBadge({ project }: { project: CodeProject }) {
  const st = projectState(project);
  const cls =
    st.tone === "ok"
      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
      : st.tone === "warning"
        ? "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300"
        : st.tone === "danger"
          ? "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300"
          : "text-muted-foreground";
  return (
    <Badge variant="outline" className={cls}>
      {st.label}
    </Badge>
  );
}

export default function ProjectsPage() {
  const [projects, setProjects] = React.useState<CodeProject[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [settings, setSettings] = React.useState<Settings | null>(null);
  const [addOpen, setAddOpen] = React.useState(false);
  const [q, setQ] = React.useState("");
  const [path, setPath] = React.useState("");
  const [name, setName] = React.useState("");
  const [nameTouched, setNameTouched] = React.useState(false);
  const [branch, setBranch] = React.useState("");
  const [branches, setBranches] = React.useState<GitLabBranch[]>([]);
  const [selectedProject, setSelectedProject] = React.useState<GitLabProject | null>(null);
  const [available, setAvailable] = React.useState<GitLabProject[]>([]);
  const [loadingAvailable, setLoadingAvailable] = React.useState(false);
  const [loadingBranches, setLoadingBranches] = React.useState(false);
  const [lookupLoading, setLookupLoading] = React.useState(false);
  const [availableError, setAvailableError] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [checking, setChecking] = React.useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = React.useState<CodeProject | null>(null);
  const [deleting, setDeleting] = React.useState(false);

  const load = React.useCallback(() => {
    setLoading(true);
    Promise.all([api.projects(), api.settings()])
      .then(([ps, s]) => {
        setProjects(ps);
        setSettings(s);
      })
      .catch((e) => toast.error("读取项目失败：" + (e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  const filtered = React.useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return projects;
    return projects.filter(
      (p) => p.name.toLowerCase().includes(needle) || p.path.toLowerCase().includes(needle),
    );
  }, [projects, q]);

  const configured = !!settings?.gitlab_configured;

  async function loadAvailable(search = "") {
    setLoadingAvailable(true);
    setAvailableError("");
    try {
      setAvailable(await api.gitlabProjects(search));
    } catch (e) {
      setAvailableError((e as Error).message);
    } finally {
      setLoadingAvailable(false);
    }
  }

  function openAdd() {
    setAddOpen(true);
    setPath("");
    setName("");
    setNameTouched(false);
    setBranch("");
    setBranches([]);
    setSelectedProject(null);
    setQ("");
    setAvailable([]);
    setAvailableError("");
    if (configured) void loadAvailable("");
  }

  function defaultProjectName(p: GitLabProject, b: string) {
    return `${p.name} · ${b || p.default_branch || "main"}`;
  }

  async function loadBranchesFor(p: GitLabProject, preferred?: string, forceName = false) {
    setLoadingBranches(true);
    try {
      const list = await api.gitlabBranches(p.id);
      setBranches(list);
      const wanted = (preferred || p.default_branch || list[0]?.name || "").trim();
      const chosen = list.some((b) => b.name === wanted) ? wanted : list[0]?.name || wanted;
      setBranch(chosen);
      if (forceName || !nameTouched) setName(defaultProjectName(p, chosen));
    } catch (e) {
      setBranches([]);
      toast.error("读取分支失败：" + (e as Error).message);
    } finally {
      setLoadingBranches(false);
    }
  }

  function chooseProject(p: GitLabProject) {
    setSelectedProject(p);
    setPath(p.path_with_namespace);
    setNameTouched(false);
    setName(defaultProjectName(p, p.default_branch || "main"));
    setBranch(p.default_branch || "main");
    void loadBranchesFor(p, p.default_branch, true);
  }

  async function lookupProject() {
    const value = path.trim();
    if (!value) {
      toast.error("请填写 GitLab 项目路径");
      return;
    }
    setLookupLoading(true);
    try {
      chooseProject(await api.gitlabLookupProject(value));
    } catch (e) {
      toast.error("解析项目失败：" + (e as Error).message);
    } finally {
      setLookupLoading(false);
    }
  }

  function chooseBranch(value: string) {
    setBranch(value);
    if (!nameTouched && selectedProject) {
      setName(defaultProjectName(selectedProject, value));
    }
  }

  async function addProject() {
    const value = path.trim();
    if (!value) {
      toast.error("请填写 GitLab 项目路径");
      return;
    }
    if (!selectedProject) {
      toast.error("请先解析项目并选择分支");
      return;
    }
    if (!branch.trim()) {
      toast.error("请选择分支");
      return;
    }
    setSaving(true);
    try {
      const p = await api.createProject({
        path: value,
        name: name.trim() || defaultProjectName(selectedProject, branch),
        branch,
      });
      toast.success(`已添加项目：${p.name}`);
      setAddOpen(false);
      load();
    } catch (e) {
      toast.error("添加项目失败：" + (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function check(id: number) {
    setChecking(id);
    try {
      const p = await api.checkProject(id);
      setProjects((prev) => prev.map((x) => (x.id === p.id ? p : x)));
      toast.success(p.last_check_error ? "检查失败：" + p.last_check_error : "已检查项目分支 HEAD");
    } catch (e) {
      toast.error("检查失败：" + (e as Error).message);
    } finally {
      setChecking(null);
    }
  }

  async function removeProject() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.deleteProject(deleteTarget.id);
      setProjects((prev) => prev.filter((p) => p.id !== deleteTarget.id));
      toast.success(`已删除项目：${deleteTarget.name}`);
      setDeleteTarget(null);
    } catch (e) {
      toast.error("删除项目失败：" + (e as Error).message);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">项目</h1>
          <p className="text-muted-foreground text-sm">
            每个项目绑定一个 GitLab 仓库和分支；同一仓库的不同分支可以建成不同项目。
          </p>
        </div>
        <Button onClick={openAdd}>
          <PlusIcon className="size-4" />
          添加项目
        </Button>
      </div>

      {!configured && (
        <Card className="border-amber-500/30 bg-amber-500/5">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div className="flex items-start gap-3">
              <AlertTriangleIcon className="mt-0.5 size-5 text-amber-600" />
              <div>
                <div className="text-sm font-medium">尚未配置 GitLab Token</div>
                <div className="text-muted-foreground text-sm">
                  配置系统级 GitLab 地址和 Token 后，才能读取项目、检查更新和拉取源码。
                </div>
              </div>
            </div>
            <Button variant="outline" asChild>
              <Link href="/system/settings">
                <Settings2Icon className="size-4" />
                去系统配置
              </Link>
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-full max-w-sm">
          <SearchIcon className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜索项目名称或路径"
            className="pl-9"
          />
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCwIcon className={loading ? "size-4 animate-spin" : "size-4"} />
          刷新
        </Button>
      </div>

      {loading ? (
        <Card>
          <CardContent className="text-muted-foreground flex items-center justify-center gap-2 py-16 text-sm">
            <Loader2Icon className="size-4 animate-spin" />
            正在读取项目…
          </CardContent>
        </Card>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-16 text-center">
            <div className="bg-muted flex size-12 items-center justify-center rounded-full">
              <FolderGit2Icon className="text-muted-foreground size-6" />
            </div>
            <div>
              <div className="font-medium">{projects.length === 0 ? "还没有项目" : "没有匹配的项目"}</div>
              <div className="text-muted-foreground mt-1 text-sm">
                {projects.length === 0
                  ? "从 GitLab 添加一个项目，作为全量与增量审计的主线。"
                  : "换一个关键词试试。"}
              </div>
            </div>
            {projects.length === 0 && (
              <Button onClick={openAdd}>
                <PlusIcon className="size-4" />
                添加项目
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((p) => (
            <Card key={p.id} className="group transition-colors hover:border-foreground/20">
              <CardHeader className="gap-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <CardTitle className="truncate text-base">{p.name}</CardTitle>
                    <CardDescription className="truncate font-mono text-xs">{p.path}</CardDescription>
                  </div>
                  <StateBadge project={p} />
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                  <span className="inline-flex items-center gap-1">
                    <GitBranchIcon className="size-3.5" />
                    {p.tracked_branch || p.default_branch || "main"}
                  </span>
                  <span>HEAD {shortCommit(p.last_seen_commit)}</span>
                  <span>上次审计 {shortCommit(p.last_audited_commit)}</span>
                </div>
                {p.last_check_error && (
                  <div className="line-clamp-2 text-xs text-red-600 dark:text-red-400">{p.last_check_error}</div>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => check(p.id)} disabled={checking === p.id}>
                    {checking === p.id ? (
                      <Loader2Icon className="size-3.5 animate-spin" />
                    ) : (
                      <CheckCircle2Icon className="size-3.5" />
                    )}
                    检查更新
                  </Button>
                  <Button variant="ghost" size="sm" asChild>
                    <Link href={`/function/projects/detail?id=${p.id}`}>
                      详情
                      <ArrowRightIcon className="size-3.5" />
                    </Link>
                  </Button>
                  {p.web_url && (
                    <Button variant="ghost" size="sm" asChild>
                      <a href={p.web_url} target="_blank" rel="noreferrer">
                        <ExternalLinkIcon className="size-3.5" />
                        GitLab
                      </a>
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    onClick={() => setDeleteTarget(p)}
                  >
                    <Trash2Icon className="size-3.5" />
                    删除
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="overflow-x-hidden sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>添加 GitLab 项目</DialogTitle>
            <DialogDescription className="break-words">
              选择仓库和分支，并给项目起名。分支是项目身份的一部分：同一仓库的
              <code className="mx-1 rounded bg-muted px-1">master</code> 和
              <code className="mx-1 rounded bg-muted px-1">test-branch</code>
              可以分别建成两个项目。
            </DialogDescription>
          </DialogHeader>

          {!configured ? (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
              系统尚未配置 GitLab Token。请先到{" "}
              <Link href="/system/settings" className="font-medium underline underline-offset-2">
                系统配置
              </Link>{" "}
              填写地址和 Token。
            </div>
          ) : (
            <div className="min-w-0 space-y-4">
              <div className="space-y-2">
                <Label htmlFor="project-path">仓库路径</Label>
                <div className="flex min-w-0 gap-2">
                  <Input
                    id="project-path"
                    value={path}
                    onChange={(e) => {
                      setPath(e.target.value);
                      setSelectedProject(null);
                      setBranches([]);
                      setBranch("");
                    }}
                    placeholder="group/project 或 group/subgroup/project"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void lookupProject();
                    }}
                  />
                  <Button type="button" variant="outline" className="shrink-0" onClick={() => void lookupProject()} disabled={lookupLoading}>
                    {lookupLoading && <Loader2Icon className="size-4 animate-spin" />}
                    解析
                  </Button>
                </div>
                {selectedProject && (
                  <div className="text-muted-foreground min-w-0 break-all text-xs">
                    已解析：{selectedProject.path_with_namespace} · 默认分支 {selectedProject.default_branch || "main"}
                  </div>
                )}
              </div>

              <div className="grid min-w-0 gap-3 sm:grid-cols-2">
                <div className="min-w-0 space-y-2">
                  <Label htmlFor="project-branch">审计分支</Label>
                  <Select value={branch} onValueChange={chooseBranch} disabled={!selectedProject || loadingBranches}>
                    <SelectTrigger id="project-branch" className="w-full min-w-0">
                      <SelectValue placeholder={loadingBranches ? "读取分支…" : "先解析项目"} />
                    </SelectTrigger>
                    <SelectContent>
                      {branches.map((b) => (
                        <SelectItem key={b.name} value={b.name}>
                          {b.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="min-w-0 space-y-2">
                  <Label htmlFor="project-name">项目名称</Label>
                  <Input
                    id="project-name"
                    value={name}
                    onChange={(e) => {
                      setNameTouched(true);
                      setName(e.target.value);
                    }}
                    placeholder="例如：诊所后端 · test-branch"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <Label>可访问项目</Label>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void loadAvailable(q)}
                    disabled={loadingAvailable}
                  >
                    {loadingAvailable ? (
                      <Loader2Icon className="size-3.5 animate-spin" />
                    ) : (
                      <SearchIcon className="size-3.5" />
                    )}
                    搜索
                  </Button>
                </div>
                <div className="relative">
                  <SearchIcon className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
                  <Input
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void loadAvailable(q);
                    }}
                    placeholder="搜索 GitLab 项目"
                    className="pl-9"
                  />
                </div>
                <div className="max-h-48 overflow-x-hidden overflow-y-auto rounded-lg border">
                  {availableError ? (
                    <div className="p-3 text-sm text-red-600 dark:text-red-400">{availableError}</div>
                  ) : loadingAvailable ? (
                    <div className="text-muted-foreground flex items-center gap-2 p-3 text-sm">
                      <Loader2Icon className="size-4 animate-spin" />
                      正在读取…
                    </div>
                  ) : available.length === 0 ? (
                    <div className="text-muted-foreground p-3 text-sm">没有可访问项目，或尚未搜索。</div>
                  ) : (
                    available.map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => chooseProject(p)}
                        disabled={saving}
                        className={`hover:bg-muted flex w-full items-start justify-between gap-3 border-b px-3 py-2 text-left text-sm last:border-b-0 disabled:opacity-50 ${
                          selectedProject?.id === p.id ? "bg-muted/60" : ""
                        }`}
                      >
                        <span className="min-w-0">
                          <span className="block truncate font-medium">{p.name}</span>
                          <span className="text-muted-foreground block truncate font-mono text-xs">
                            {p.path_with_namespace}
                          </span>
                        </span>
                        <span className="text-muted-foreground shrink-0 text-xs">{p.default_branch || "main"}</span>
                      </button>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>
              取消
            </Button>
            {configured && (
              <Button
                onClick={() => void addProject()}
                disabled={saving || !path.trim() || !selectedProject || !branch || loadingBranches}
              >
                {saving && <Loader2Icon className="size-4 animate-spin" />}
                添加
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open && !deleting) setDeleteTarget(null);
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>删除项目</DialogTitle>
            <DialogDescription className="break-words">
              确认删除项目「{deleteTarget?.name}」？相关审计记录会一并移除，已创建的执行任务不会自动删除。
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-md border bg-muted/30 px-3 py-2 font-mono text-xs">
            {deleteTarget?.path}
            <span className="text-muted-foreground"> · {deleteTarget?.tracked_branch || deleteTarget?.default_branch || "main"}</span>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)} disabled={deleting}>
              取消
            </Button>
            <Button variant="destructive" onClick={() => void removeProject()} disabled={deleting}>
              {deleting && <Loader2Icon className="size-4 animate-spin" />}
              删除项目
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
