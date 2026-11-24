package server

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/Autumn-27/artex/db"
)

// taskChainObservations returns deferred worker facts that look like cross-endpoint
// chain risks. This is intentionally separate from the endpoint × vuln matrix:
// chains are follow-up material, not cells that should reopen a completed matrix.
func (s *Server) taskChainObservations(w http.ResponseWriter, r *http.Request) {
	t, ok := s.resolveVisibleTask(currentUser(r), r.PathValue("id"))
	if !ok || t == nil {
		writeErr(w, http.StatusNotFound, "task not found")
		return
	}
	out, err := s.taskChainObservationNodes(t)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"observations": taskNodeDTOs(out)})
}

func (s *Server) taskChainObservationNodes(t *Task) ([]*db.Node, error) {
	facts, err := t.Store.ListByKind(db.KindFact, 10000)
	if err != nil {
		return nil, err
	}
	out := make([]*db.Node, 0)
	for _, fact := range facts {
		if isChainObservation(fact.Payload) {
			out = append(out, fact)
		}
	}
	return out, nil
}

func isChainObservation(raw json.RawMessage) bool {
	var payload struct {
		Kind    string `json:"kind"`
		Chain   bool   `json:"chain"`
		Summary string `json:"summary"`
		Detail  string `json:"detail"`
	}
	if len(raw) > 0 {
		_ = json.Unmarshal(raw, &payload)
	}
	if strings.EqualFold(strings.TrimSpace(payload.Kind), "chain") || payload.Chain {
		return true
	}
	text := payload.Summary + "\n" + payload.Detail
	return strings.Contains(text, "链式") || strings.Contains(text, "二阶")
}

type chainAuditRequest struct {
	ObservationIDs []string `json:"observation_ids"`
}

// auditTaskChainObservations creates a follow-up task for one selected chain
// observation, or for all current chain observations when no id is supplied.
// The source tree is copied from the originating task; the matrix is not reopened.
func (s *Server) auditTaskChainObservations(w http.ResponseWriter, r *http.Request) {
	t, ok := s.resolveVisibleTask(currentUser(r), r.PathValue("id"))
	if !ok || t == nil {
		writeErr(w, http.StatusNotFound, "task not found")
		return
	}
	me := currentUser(r)
	if me == nil {
		writeErr(w, http.StatusUnauthorized, "未授权")
		return
	}
	if access := s.taskAccessFor(me, t); !access.Write {
		writeErr(w, http.StatusForbidden, "当前账号对该任务只有读权限")
		return
	}
	if ok, err := s.canCreateTask(me); err != nil {
		writeErr(w, http.StatusInternalServerError, err.Error())
		return
	} else if !ok {
		writeErr(w, http.StatusForbidden, "当前账号没有创建任务的权限")
		return
	}
	if strings.TrimSpace(t.SourcePath) == "" {
		writeErr(w, http.StatusConflict, "原任务没有源码目录，无法开启链式审计")
		return
	}
	var req chainAuditRequest
	if r.Body != nil {
		_ = json.NewDecoder(r.Body).Decode(&req)
	}
	all, err := s.taskChainObservationNodes(t)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, err.Error())
		return
	}
	wanted := make(map[string]bool, len(req.ObservationIDs))
	for _, id := range req.ObservationIDs {
		if id = strings.TrimSpace(id); id != "" {
			wanted[id] = true
		}
	}
	selected := make([]*db.Node, 0, len(all))
	for _, fact := range all {
		if len(wanted) == 0 || wanted[i64s(fact.ID)] {
			selected = append(selected, fact)
		}
	}
	if len(selected) == 0 {
		writeErr(w, http.StatusBadRequest, "没有匹配的链式风险观察")
		return
	}
	sourceDir := filepath.Join(s.m.dir, filepath.FromSlash(t.SourcePath))
	if fi, statErr := os.Stat(sourceDir); statErr != nil || !fi.IsDir() {
		writeErr(w, http.StatusConflict, "原任务源码目录不存在")
		return
	}
	var summaries []string
	for _, fact := range selected {
		var payload struct {
			Summary string `json:"summary"`
			Detail  string `json:"detail"`
		}
		_ = json.Unmarshal(fact.Payload, &payload)
		summary := strings.TrimSpace(payload.Summary)
		if summary == "" {
			summary = strings.TrimSpace(payload.Detail)
		}
		if len([]rune(summary)) > 1200 {
			summary = string([]rune(summary)[:1200]) + "…"
		}
		summaries = append(summaries, fmt.Sprintf("- fact #%d: %s", fact.ID, summary))
	}
	label := "链式风险审计"
	if len(selected) == 1 {
		label += " · fact #" + i64s(selected[0].ID)
	} else {
		label += fmt.Sprintf(" · %d 项", len(selected))
	}
	description := fmt.Sprintf("%s（来源任务 #%s）", label, t.ID)
	goal := "审计以下链式风险/延后观察，重点核对它们依赖的链路、前提条件和缺失证据。\n" +
		"这是来源任务已完成矩阵后的后续审查，不要求重新打开或重审原矩阵；请以源码证据为准，结论只能是 confirmed / clean / needs_more。\n\n" +
		strings.Join(summaries, "\n")
	sourceTaskID, _ := strconv.ParseInt(t.ID, 10, 64)
	task, err := s.m.CreateTaskWithOptions(description, goal, db.TaskCreateOptions{
		Name:          fmt.Sprintf("%s · %s", t.Name, label),
		CreatedBy:     &me.ID,
		SourceTaskIDs: []int64{sourceTaskID},
		DepartmentID:  t.DepartmentID,
		AccessProfile: t.AccessProfile,
	})
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "创建链式审计任务失败："+err.Error())
		return
	}
	taskID, _ := strconv.ParseInt(task.ID, 10, 64)
	relSource := filepath.ToSlash(filepath.Join("tasks", task.ID, "source"))
	taskSource := filepath.Join(s.m.dir, filepath.FromSlash(relSource))
	cleanup := func(msg string) {
		_ = os.RemoveAll(taskSource)
		if _, delErr := s.m.DeleteTask(task.ID, DeleteTaskOptions{DeleteFiles: true}); delErr != nil {
			log.Printf("[chain-audit] 清理失败任务 #%s: %v", task.ID, delErr)
		}
		writeErr(w, http.StatusInternalServerError, msg)
	}
	if err := copyDirTree(sourceDir, taskSource); err != nil {
		cleanup("复制链式审计源码失败：" + err.Error())
		return
	}
	if err := s.m.pg.SetTaskSourcePath(taskID, relSource); err != nil {
		cleanup("记录链式审计源码目录失败：" + err.Error())
		return
	}
	s.m.SetTaskSourcePathInMemory(task.ID, relSource)
	s.launchTask(task, description+" "+goal, false)
	writeJSON(w, http.StatusAccepted, map[string]any{
		"task_id": taskID,
		"count":   len(selected),
	})
}
