package server

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/artex/gitlabsrc"
)

type incrementalDelta struct {
	ChangedFiles int
	DeltaCells   int
	Endpoints    []string
	ChangedPaths []string
}

func (s *Server) findBaseAuditTask(p *db.CodeProject) (*db.Task, *db.ProjectAuditRun, error) {
	if p == nil {
		return nil, nil, nil
	}
	// Prefer the explicit pointer written by the reconciler after the previous
	// audit completed. This is what makes the chain
	// full -> incremental -> next incremental deterministic.
	if p.LastAuditedTaskID != nil && *p.LastAuditedTaskID > 0 {
		t, err := s.m.pg.GetTask(*p.LastAuditedTaskID)
		if err != nil {
			return nil, nil, err
		}
		if t != nil && strings.TrimSpace(t.SourcePath) != "" {
			var baseRun *db.ProjectAuditRun
			if p.LastAuditedRunID != nil && *p.LastAuditedRunID > 0 {
				baseRun, err = s.m.pg.CodeProjects().GetAudit(*p.LastAuditedRunID)
				if err != nil {
					return nil, nil, err
				}
			}
			if baseRun == nil || (baseRun.ProjectID == p.ID && baseRun.TargetCommit == p.LastAuditedCommit) {
				return t, baseRun, nil
			}
		}
	}
	// Legacy fallback for projects created before last_audited_task_id existed.
	runs, err := s.m.pg.CodeProjects().ListAudits(p.ID, 100)
	if err != nil {
		return nil, nil, err
	}
	for i := range runs {
		r := &runs[i]
		if r.TaskID == nil || r.TargetCommit != p.LastAuditedCommit {
			continue
		}
		if r.Status != "audited" && r.Status != "ready" {
			continue
		}
		t, err := s.m.pg.GetTask(*r.TaskID)
		if err != nil {
			return nil, nil, err
		}
		if t != nil && strings.TrimSpace(t.SourcePath) != "" {
			return t, r, nil
		}
	}
	return nil, nil, nil
}

// POST /api/projects/{id}/incremental-prepare
func (s *Server) prepareIncrementalAudit(w http.ResponseWriter, r *http.Request) {
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
	c, err := s.gitlabClient()
	if err != nil {
		writeErr(w, 400, err.Error())
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 45*time.Second)
	defer cancel()
	b, err := c.Branch(ctx, p.GitLabProjectID, projectBranch(p))
	if err != nil {
		writeErr(w, 502, "读取项目分支失败："+err.Error())
		return
	}
	target := strings.TrimSpace(b.Commit.ID)
	if target == "" {
		writeErr(w, 502, "GitLab 返回的分支 commit 为空")
		return
	}
	base := strings.TrimSpace(p.LastAuditedCommit)
	if base == "" {
		writeErr(w, 409, "还没有成功审计基线，请先完成一次全量审计")
		return
	}
	if target == base {
		writeErr(w, 409, "目标分支没有新提交，无需增量准备")
		return
	}
	baseTask, baseRun, err := s.findBaseAuditTask(p)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	if baseTask == nil {
		writeErr(w, 409, "找不到基线 commit 对应的源码快照，请重新执行全量审计")
		return
	}
	var baseRunID *int64
	if baseRun != nil {
		id := baseRun.ID
		baseRunID = &id
	}
	// One in-flight preparation per project.
	if latest, err := s.m.pg.CodeProjects().ListAudits(id, 1); err != nil {
		writeErr(w, 500, err.Error())
		return
	} else if len(latest) > 0 && latest[0].Status == "preparing" {
		writeErr(w, 409, "该项目已有增量准备正在运行")
		return
	}
	u := currentUser(r)
	var createdBy *int64
	if u != nil {
		createdBy = &u.ID
	}
	baseTaskID := baseTask.ID
	run, err := s.m.pg.CodeProjects().StartIncrementalAudit(id, baseTaskID, baseRunID, base, target, createdBy)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	go s.runIncrementalPreparation(run, p, baseTask, target)
	log.Printf("[incremental] 项目 %s 开始准备 run=%d base=%s target=%s", p.Path, run.ID, shortCommit(base), shortCommit(target))
	writeJSON(w, http.StatusAccepted, run)
}

func (s *Server) runIncrementalPreparation(run *db.ProjectAuditRun, p *db.CodeProject, baseTask *db.Task, target string) {
	fail := func(msg string) {
		_ = s.m.pg.CodeProjects().FinishAudit(run.ID, nil, "failed", msg)
		log.Printf("[incremental] run=%d 准备失败: %s", run.ID, msg)
	}
	ctx, cancel := context.WithTimeout(s.ctx, 20*time.Minute)
	defer cancel()

	baseSource := filepath.Join(s.m.dir, filepath.FromSlash(baseTask.SourcePath))
	if fi, err := os.Stat(baseSource); err != nil || !fi.IsDir() {
		fail("基线源码快照不存在")
		return
	}
	relSource := filepath.ToSlash(filepath.Join("projects", strconv.FormatInt(p.ID, 10), "incremental", strconv.FormatInt(run.ID, 10), "source"))
	targetSource := filepath.Join(s.m.dir, filepath.FromSlash(relSource))
	if err := os.RemoveAll(targetSource); err != nil {
		fail("清理目标源码目录失败：" + err.Error())
		return
	}
	if err := os.MkdirAll(filepath.Dir(targetSource), 0o755); err != nil {
		fail("创建目标源码目录失败：" + err.Error())
		return
	}
	if err := copyDirTree(baseSource, targetSource); err != nil {
		fail("复制基线源码失败：" + err.Error())
		return
	}
	c, err := s.gitlabClient()
	if err != nil {
		fail(err.Error())
		return
	}
	cmp, err := c.Compare(ctx, p.GitLabProjectID, p.LastAuditedCommit, target)
	if err != nil {
		fail("GitLab compare 失败：" + err.Error())
		return
	}
	if cmp.CompareTimeout {
		fail("GitLab compare 超时，不能可靠计算增量")
		return
	}
	delta, err := s.applyChangedFiles(ctx, c, p, targetSource, p.LastAuditedCommit, target, cmp)
	if err != nil {
		fail(err.Error())
		return
	}
	outDir := filepath.Join(s.m.dir, "projects", strconv.FormatInt(p.ID, 10), "incremental", strconv.FormatInt(run.ID, 10), "matrix")
	body, err := s.buildMatrixImport(ctx, targetSource, outDir)
	if err != nil {
		fail("目标矩阵生成失败：" + err.Error())
		return
	}
	cellKeys := deltaCellKeys(body, delta)
	delta.DeltaCells = len(cellKeys)
	if err := s.m.pg.CodeProjects().MarkAuditPrepared(run.ID, relSource, delta.ChangedFiles, delta.DeltaCells, cellKeys); err != nil {
		fail("记录增量准备结果失败：" + err.Error())
		return
	}
	log.Printf("[incremental] run=%d 准备完成：files=%d delta_cells=%d endpoints=%v", run.ID, delta.ChangedFiles, delta.DeltaCells, delta.Endpoints)
}

func (s *Server) applyChangedFiles(ctx context.Context, c *gitlabsrc.Client, p *db.CodeProject, targetSource, baseCommit, targetCommit string, cmp *gitlabsrc.Compare) (incrementalDelta, error) {
	delta := incrementalDelta{}
	changed := map[string]bool{}
	endpoints := map[string]bool{}
	for _, d := range cmp.Diffs {
		oldPath, oldOK := safeZipPath(d.OldPath)
		newPath, newOK := safeZipPath(d.NewPath)
		if !oldOK && !newOK {
			continue
		}
		if d.DeletedFile {
			if oldOK {
				_ = os.Remove(filepath.Join(targetSource, filepath.FromSlash(oldPath)))
			}
			changed[oldPath] = true
			delta.ChangedFiles++
			continue
		}
		path := newPath
		if !newOK {
			path = oldPath
		}
		if path == "" {
			continue
		}
		if d.RenamedFile && oldOK && oldPath != path {
			_ = os.Remove(filepath.Join(targetSource, filepath.FromSlash(oldPath)))
		}
		raw, err := c.RawFile(ctx, p.GitLabProjectID, path, targetCommit)
		if err != nil {
			return delta, fmt.Errorf("读取变更文件 %s 失败：%w", path, err)
		}
		full := filepath.Join(targetSource, filepath.FromSlash(path))
		if err := os.MkdirAll(filepath.Dir(full), 0o755); err != nil {
			return delta, err
		}
		if err := os.WriteFile(full, raw, 0o644); err != nil {
			return delta, err
		}
		changed[path] = true
		delta.ChangedFiles++
		if strings.HasSuffix(strings.ToLower(path), ".java") {
			for _, ep := range parseSpringEndpoints(raw, path) {
				endpoints[ep.Method+" "+ep.Path] = true
			}
		}
	}
	delta.Endpoints = make([]string, 0, len(endpoints))
	for ep := range endpoints {
		delta.Endpoints = append(delta.Endpoints, ep)
	}
	delta.ChangedPaths = make([]string, 0, len(changed))
	for p := range changed {
		delta.ChangedPaths = append(delta.ChangedPaths, p)
	}
	return delta, nil
}

func deltaCellKeys(body importCellsBody, delta incrementalDelta) []string {
	changedPaths := map[string]bool{}
	changedBases := map[string]bool{}
	for _, p := range delta.ChangedPaths {
		p = strings.ToLower(strings.TrimPrefix(p, "/"))
		changedPaths[p] = true
		changedBases[filepath.Base(p)] = true
	}
	endpointPaths := map[string]bool{}
	for _, ep := range delta.Endpoints {
		if i := strings.IndexByte(ep, ' '); i >= 0 {
			endpointPaths[ep[i+1:]] = true
		}
	}
	keys := []string{}
	for _, cell := range body.Tasks {
		if cell.Eligibility != "applicable" && cell.Eligibility != "unverified" && cell.Eligibility != "needs_review" {
			continue
		}
		hit := endpointPaths[cell.Endpoint.URL]
		if !hit {
			for _, f := range deltaEndpointsFromHints(cell.Hints) {
				f = strings.ToLower(strings.TrimPrefix(f, "/"))
				if changedPaths[f] || changedBases[filepath.Base(f)] {
					hit = true
					break
				}
			}
		}
		if !hit {
			// Repo-level cells sometimes carry only a short site string.
			blob := strings.ToLower(string(cell.Hints) + " " + cell.Direction)
			for base := range changedBases {
				if base != "" && strings.Contains(blob, base) {
					hit = true
					break
				}
			}
		}
		if hit {
			keys = append(keys, cell.CellKey)
		}
	}
	sort.Strings(keys)
	return keys
}

func deltaEndpointsFromHints(raw json.RawMessage) []string {
	var h struct {
		Flow []struct {
			File string `json:"file"`
		} `json:"flow"`
		Sites []struct {
			File string `json:"file"`
		} `json:"sites"`
	}
	if json.Unmarshal(raw, &h) != nil {
		return nil
	}
	var out []string
	for _, f := range h.Flow {
		out = append(out, f.File)
	}
	for _, s := range h.Sites {
		out = append(out, s.File)
	}
	return out
}

// POST /api/projects/{id}/incremental-runs/{runID}/start
//
// A prepared run has already copied the target source and generated the target
// matrix. Starting it must not download the archive again or regenerate the
// matrix. Only the persisted delta cells are imported into the task, so the
// unchanged target cells keep their base-task conclusions.
func (s *Server) startPreparedIncrementalAudit(w http.ResponseWriter, r *http.Request) {
	projectID, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil || projectID <= 0 {
		writeErr(w, 400, "项目 ID 不合法")
		return
	}
	runID, err := strconv.ParseInt(r.PathValue("runID"), 10, 64)
	if err != nil || runID <= 0 {
		writeErr(w, 400, "增量运行 ID 不合法")
		return
	}
	p, err := s.m.pg.CodeProjects().Get(projectID)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	if p == nil {
		writeErr(w, 404, "项目不存在")
		return
	}
	run, err := s.m.pg.CodeProjects().GetAudit(runID)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	if run == nil || run.ProjectID != projectID {
		writeErr(w, 404, "增量运行不存在")
		return
	}
	if run.Status != "prepared" {
		writeErr(w, 409, "增量运行不是 prepared 状态")
		return
	}
	if strings.TrimSpace(p.LastAuditedCommit) != strings.TrimSpace(run.BaseCommit) {
		writeErr(w, 409, "项目审计基线已变化，请重新准备本次增量")
		return
	}
	if run.BaseTaskID == nil || *run.BaseTaskID <= 0 {
		writeErr(w, 409, "增量运行缺少基线任务")
		return
	}
	if len(run.DeltaCellKeys) == 0 {
		writeErr(w, 409, "该增量运行没有 delta 明细，请重新准备")
		return
	}
	if strings.TrimSpace(run.SourcePath) == "" {
		writeErr(w, 409, "增量运行缺少源码快照")
		return
	}
	sourceDir := filepath.Join(s.m.dir, filepath.FromSlash(run.SourcePath))
	if fi, statErr := os.Stat(sourceDir); statErr != nil || !fi.IsDir() {
		writeErr(w, 409, "增量源码快照不存在，请重新准备")
		return
	}
	matrixPath := filepath.Join(filepath.Dir(sourceDir), "matrix", "import.json")
	raw, err := os.ReadFile(matrixPath)
	if err != nil {
		writeErr(w, 409, "增量矩阵文件不存在，请重新准备")
		return
	}
	var fullBody importCellsBody
	if err := json.Unmarshal(raw, &fullBody); err != nil {
		writeErr(w, 500, "解析增量矩阵失败："+err.Error())
		return
	}
	allowed := make(map[string]bool, len(run.DeltaCellKeys))
	for _, key := range run.DeltaCellKeys {
		if key = strings.TrimSpace(key); key != "" {
			allowed[key] = true
		}
	}
	body := fullBody
	body.Tasks = make([]db.CellInput, 0, len(run.DeltaCellKeys))
	for _, cell := range fullBody.Tasks {
		if allowed[cell.CellKey] {
			body.Tasks = append(body.Tasks, cell)
		}
	}
	if len(body.Tasks) == 0 {
		writeErr(w, 409, "delta 明细没有匹配到目标矩阵，请重新准备")
		return
	}
	// Reject a second live run for the same project. Prepared runs are inert and
	// may stay around, but only one task may be executing at a time.
	if runs, listErr := s.m.pg.CodeProjects().ListAudits(projectID, 10); listErr != nil {
		writeErr(w, 500, listErr.Error())
		return
	} else {
		for _, other := range runs {
			if other.ID == run.ID {
				continue
			}
			if other.Status == "fetching" || other.Status == "preparing" || other.Status == "running" {
				writeErr(w, 409, "该项目已有审计运行正在进行")
				return
			}
		}
	}
	me := currentUser(r)
	if me == nil {
		writeErr(w, 401, "未授权")
		return
	}
	if ok, permErr := s.canCreateTask(me); permErr != nil {
		writeErr(w, 500, permErr.Error())
		return
	} else if !ok {
		writeErr(w, 403, "当前账号没有创建任务的权限")
		return
	}
	baseTask, err := s.m.pg.GetTask(*run.BaseTaskID)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	if baseTask == nil || strings.TrimSpace(baseTask.SourcePath) == "" {
		writeErr(w, 409, "基线任务源码不存在，请重新准备")
		return
	}
	var req struct {
		AutoStart *bool `json:"auto_start"`
	}
	if r.Body != nil {
		_ = json.NewDecoder(r.Body).Decode(&req)
	}
	autoStart := req.AutoStart == nil || *req.AutoStart
	desc := fmt.Sprintf("增量审计 GitLab 项目 %s（%s @ %s，base %s）", p.Path, projectBranch(p), shortSHA(run.TargetCommit), shortSHA(run.BaseCommit))
	goal := "只审计本次增量矩阵格（变更文件影响的接口与漏洞类型）；未变更矩阵格的结论从基线任务只读继承，不重新审计、不发请求、不编译业务源码。"
	task, err := s.m.CreateTaskWithOptions(desc, goal, db.TaskCreateOptions{
		Name:          fmt.Sprintf("%s · 增量审计 %s", p.Name, shortSHA(run.TargetCommit)),
		CreatedBy:     &me.ID,
		SourceTaskIDs: []int64{*run.BaseTaskID},
	})
	if err != nil {
		writeErr(w, 500, "创建增量任务失败："+err.Error())
		return
	}
	taskID, _ := strconv.ParseInt(task.ID, 10, 64)
	relSource := filepath.ToSlash(filepath.Join("tasks", task.ID, "source"))
	taskSource := filepath.Join(s.m.dir, filepath.FromSlash(relSource))
	cleanup := func(msg string) {
		_ = os.RemoveAll(taskSource)
		if _, delErr := s.m.DeleteTask(task.ID, DeleteTaskOptions{DeleteFiles: true}); delErr != nil {
			log.Printf("[incremental] 清理失败任务 #%s: %v", task.ID, delErr)
		}
		_ = s.m.pg.CodeProjects().FinishAudit(run.ID, nil, "failed", msg)
		log.Printf("[incremental] run=%d 启动失败: %s", run.ID, msg)
		writeErr(w, 500, msg)
	}
	if err := copyDirTree(sourceDir, taskSource); err != nil {
		cleanup("复制增量源码到任务失败：" + err.Error())
		return
	}
	if err := s.m.pg.SetTaskSourcePath(taskID, relSource); err != nil {
		cleanup("记录任务源码目录失败：" + err.Error())
		return
	}
	s.m.SetTaskSourcePathInMemory(task.ID, relSource)
	if _, _, err := s.importMatrixCells(task, body); err != nil {
		cleanup("导入增量矩阵失败：" + err.Error())
		return
	}
	_ = s.m.SetTaskMatrixState(task.ID, "ready", "")
	if err := s.m.pg.CodeProjects().FinishAudit(run.ID, &taskID, "running", ""); err != nil {
		cleanup("更新增量运行状态失败：" + err.Error())
		return
	}
	if autoStart {
		s.launchTask(task, desc+" "+goal, false)
	}
	log.Printf("[incremental] run=%d 启动任务 #%s target=%s delta_cells=%d inherited_source=%d", run.ID, task.ID, shortSHA(run.TargetCommit), len(body.Tasks), *run.BaseTaskID)
	updated, _ := s.m.pg.CodeProjects().GetAudit(run.ID)
	writeJSON(w, http.StatusAccepted, map[string]any{
		"audit":   updated,
		"task_id": taskID,
	})
}
