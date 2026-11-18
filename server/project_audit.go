package server

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/artex/gitlabsrc"
)

// POST /api/projects/{id}/audit
//
// v1 only implements mode=full. Incremental is deliberately rejected instead of
// silently falling back to a full scan: a caller that asked for a delta must not
// get a completely different audit shape without knowing it.
func (s *Server) startProjectAudit(w http.ResponseWriter, r *http.Request) {
	me := currentUser(r)
	if me == nil {
		writeErr(w, 401, "未授权")
		return
	}
	if ok, err := s.canCreateTask(me); err != nil {
		writeErr(w, 500, err.Error())
		return
	} else if !ok {
		writeErr(w, 403, "当前账号没有创建任务的权限")
		return
	}
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil || id <= 0 {
		writeErr(w, 400, "项目 ID 不合法")
		return
	}
	p, err := s.m.pg.CodeProjects().Get(id)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	if p == nil {
		writeErr(w, 404, "项目不存在")
		return
	}
	var req struct {
		Mode      string `json:"mode"`
		AutoStart *bool  `json:"auto_start"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, 400, "请求格式不正确")
		return
	}
	mode := strings.TrimSpace(req.Mode)
	if mode == "" {
		mode = "full"
	}
	if mode != "full" {
		writeErr(w, 501, "增量审计将在下一阶段接入；当前请先发起全量审计")
		return
	}
	if p.GitLabProjectID <= 0 {
		writeErr(w, 400, "项目缺少 GitLab 项目 ID，请重新从 GitLab 添加")
		return
	}
	// One in-flight run per project keeps source staging and baseline updates
	// unambiguous. The UI can retry after the current run finishes or fails.
	if latest, err := s.m.pg.CodeProjects().ListAudits(id, 1); err != nil {
		writeErr(w, 500, err.Error())
		return
	} else if len(latest) > 0 && latest[0].Status == "fetching" {
		writeErr(w, 409, "该项目已有审计正在准备源码，请等待完成")
		return
	}
	c, err := s.gitlabClient()
	if err != nil {
		writeErr(w, 400, err.Error())
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 45*time.Second)
	defer cancel()
	branch := projectBranch(p)
	b, err := c.Branch(ctx, p.GitLabProjectID, branch)
	if err != nil {
		writeErr(w, 502, "读取项目分支失败："+err.Error())
		return
	}
	target := strings.TrimSpace(b.Commit.ID)
	if target == "" {
		writeErr(w, 502, "GitLab 返回的分支 commit 为空")
		return
	}
	run, err := s.m.pg.CodeProjects().StartAudit(id, "full", p.LastAuditedCommit, target, &me.ID)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	uploadID := newUploadID()
	dir := filepath.Join(s.m.dir, uploadDirName, uploadID)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		_ = s.m.pg.CodeProjects().FinishAudit(run.ID, nil, "failed", "创建源码目录失败："+err.Error())
		writeErr(w, 500, "创建源码目录失败")
		return
	}
	zipPath := filepath.Join(dir, "download.zip")
	sourceDir := filepath.Join(dir, "source")
	createdBy := me.ID
	up, err := s.m.pg.TaskUploads().CreateTaskUpload(db.NewTaskUpload{
		ID:             uploadID,
		Filename:       fmt.Sprintf("%s@%s.zip", p.Path, shortSHA(target)),
		StoredPath:     zipPath,
		SourcePath:     sourceDir,
		CreatedBy:      &createdBy,
		Origin:         "github", // existing task-detail source badge uses this value
		SourceURL:      p.WebURL,
		SourceRef:      branch,
		ResolvedCommit: target,
		State:          db.UploadStateFetching,
	})
	if err != nil {
		_ = os.RemoveAll(dir)
		_ = s.m.pg.CodeProjects().FinishAudit(run.ID, nil, "failed", "记录源码任务失败："+err.Error())
		writeErr(w, 500, "记录源码任务失败："+err.Error())
		return
	}
	autoStart := req.AutoStart == nil || *req.AutoStart
	// Keep the context override out of the request lifetime: the request returns
	// immediately, but the download may take minutes.
	go s.runProjectFullAudit(run, p, me, c, up.ID, zipPath, sourceDir, target, autoStart)
	log.Printf("[project] 项目 %s 发起全量审计 run=%d target=%s upload=%s", p.Path, run.ID, shortSHA(target), uploadID)
	writeJSON(w, http.StatusAccepted, map[string]any{
		"audit":     run,
		"upload_id": uploadID,
		"state":     db.UploadStateFetching,
	})
}

func (s *Server) runProjectFullAudit(run *db.ProjectAuditRun, p *db.CodeProject, me *db.User, c *gitlabsrc.Client, uploadID, zipPath, sourceDir, target string, autoStart bool) {
	var task *Task
	fail := func(msg string) {
		_ = s.m.pg.TaskUploads().MarkTaskUploadFailed(uploadID, msg)
		_ = os.RemoveAll(filepath.Join(s.m.dir, uploadDirName, uploadID))
		if task != nil {
			if _, err := s.m.DeleteTask(task.ID, DeleteTaskOptions{DeleteFiles: true}); err != nil {
				log.Printf("[project] 清理失败任务 #%s: %v", task.ID, err)
			}
		}
		_ = s.m.pg.CodeProjects().FinishAudit(run.ID, nil, "failed", msg)
		log.Printf("[project] 项目 %s 全量审计失败: %s", p.Path, msg)
	}
	ctx, cancel := context.WithTimeout(s.ctx, 30*time.Minute)
	defer cancel()
	n, err := c.DownloadArchive(ctx, p.GitLabProjectID, target, zipPath)
	if err != nil {
		fail("下载源码失败：" + err.Error())
		return
	}
	stats, err := extractZipArchiveOpts(zipPath, sourceDir, extractOptions{
		WrapperPrefix: gitlabArchiveWrapper(p.Path),
		MaxBytes:      -1,
		MaxFiles:      -1,
		Context:       ctx,
	})
	if err != nil {
		fail("解压源码失败：" + err.Error())
		return
	}
	if stats.Files == 0 {
		fail("源码归档为空")
		return
	}
	if _, err := s.m.pg.TaskUploads().MarkTaskUploadReady(uploadID, n, stats.Files, stats.Bytes); err != nil {
		fail("标记源码就绪失败：" + err.Error())
		return
	}
	desc := fmt.Sprintf("审计 GitLab 项目 %s（%s @ %s）", p.Path, projectBranch(p), shortSHA(target))
	goal := "对该项目源码进行全量静态代码审计，优先检查 Java 代码中的安全缺陷；结论必须有源码证据，不运行应用、不发请求、不编译业务源码。"
	t, err := s.m.CreateTaskWithOptions(desc, goal, db.TaskCreateOptions{
		Name:      fmt.Sprintf("%s · 全量审计 %s", p.Name, shortSHA(target)),
		CreatedBy: &me.ID,
	})
	if err != nil {
		fail("创建审计任务失败：" + err.Error())
		return
	}
	task = t
	if err := s.attachUploadToTask(me, task, uploadID); err != nil {
		fail("绑定源码失败：" + err.Error())
		return
	}
	if err := s.m.pg.CodeProjects().MarkAudited(p.ID, target); err != nil {
		fail("更新项目审计基线失败：" + err.Error())
		return
	}
	taskID, _ := strconv.ParseInt(task.ID, 10, 64)
	if err := s.m.pg.CodeProjects().FinishAudit(run.ID, &taskID, "ready", ""); err != nil {
		log.Printf("[project] 更新审计运行失败: %v", err)
	}
	_ = os.Remove(zipPath)
	if autoStart {
		s.launchTask(task, desc+" "+goal, false)
	}
	log.Printf("[project] 项目 %s 全量审计已创建任务 #%s target=%s auto_start=%v", p.Path, task.ID, shortSHA(target), autoStart)
}

// gitlabArchiveWrapper returns the slug prefix GitLab uses for the single
// top-level directory in an archive. GitLab uses the project path's last
// segment (the `path` field), not the full `group/project` string.
func gitlabArchiveWrapper(projectPath string) string {
	projectPath = strings.Trim(strings.TrimSpace(projectPath), "/")
	if i := strings.LastIndexByte(projectPath, '/'); i >= 0 {
		projectPath = projectPath[i+1:]
	}
	if projectPath == "" {
		return ""
	}
	return projectPath + "-"
}

func (s *Server) listProjectAudits(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil || id <= 0 {
		writeErr(w, 400, "项目 ID 不合法")
		return
	}
	p, err := s.m.pg.CodeProjects().Get(id)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	if p == nil {
		writeErr(w, 404, "项目不存在")
		return
	}
	runs, err := s.m.pg.CodeProjects().ListAudits(id, 30)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	writeJSON(w, 200, map[string]any{"audits": runs})
}

func (s *Server) getProjectAudit(w http.ResponseWriter, r *http.Request) {
	projectID, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil || projectID <= 0 {
		writeErr(w, 400, "项目 ID 不合法")
		return
	}
	runID, err := strconv.ParseInt(r.PathValue("runID"), 10, 64)
	if err != nil || runID <= 0 {
		writeErr(w, 400, "审计运行 ID 不合法")
		return
	}
	run, err := s.m.pg.CodeProjects().GetAudit(runID)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	if run == nil || run.ProjectID != projectID {
		writeErr(w, 404, "审计运行不存在")
		return
	}
	writeJSON(w, 200, run)
}
