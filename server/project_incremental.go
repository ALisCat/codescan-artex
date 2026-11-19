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

type incrementalDelta struct {
	ChangedFiles int
	DeltaCells   int
	Endpoints    []string
	ChangedPaths []string
}

func (s *Server) findBaseAuditTask(projectID int64, baseCommit string) (*db.Task, error) {
	runs, err := s.m.pg.CodeProjects().ListAudits(projectID, 100)
	if err != nil {
		return nil, err
	}
	for _, r := range runs {
		if r.TaskID == nil || r.TargetCommit != baseCommit {
			continue
		}
		if r.Status != "audited" && r.Status != "ready" {
			continue
		}
		t, err := s.m.pg.GetTask(*r.TaskID)
		if err != nil {
			return nil, err
		}
		if t != nil && strings.TrimSpace(t.SourcePath) != "" {
			return t, nil
		}
	}
	return nil, nil
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
	baseTask, err := s.findBaseAuditTask(id, base)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	if baseTask == nil {
		writeErr(w, 409, "找不到基线 commit 对应的源码快照，请重新执行全量审计")
		return
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
	run, err := s.m.pg.CodeProjects().StartIncrementalAudit(id, baseTaskID, base, target, createdBy)
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
	delta.DeltaCells = countDeltaCells(body, delta)
	if err := s.m.pg.CodeProjects().MarkAuditPrepared(run.ID, relSource, delta.ChangedFiles, delta.DeltaCells); err != nil {
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

func countDeltaCells(body importCellsBody, delta incrementalDelta) int {
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
	n := 0
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
			n++
		}
	}
	return n
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
