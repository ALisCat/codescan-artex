package server

import (
	"log"
	"time"
)

const projectAuditReconcileInterval = 30 * time.Second

// startProjectAuditReconciler moves a project's last_audited_commit only after
// the task created by a project audit really finished. Before this, the baseline
// was written at task creation time, which could leave a false baseline when the
// task later failed.
func (s *Server) startProjectAuditReconciler() {
	if s == nil || s.ctx == nil {
		return
	}
	go func() {
		timer := time.NewTimer(10 * time.Second)
		defer timer.Stop()
		for {
			select {
			case <-s.ctx.Done():
				return
			case <-timer.C:
				s.reconcileProjectAudits()
				timer.Reset(projectAuditReconcileInterval)
			}
		}
	}()
}

func (s *Server) reconcileProjectAudits() {
	runs, err := s.m.pg.CodeProjects().ListPendingAuditRuns(200)
	if err != nil {
		log.Printf("[project] 读取待收尾审计运行失败: %v", err)
		return
	}
	for _, run := range runs {
		if run.TaskID == nil || *run.TaskID <= 0 {
			continue
		}
		t, err := s.m.pg.GetTask(*run.TaskID)
		if err != nil {
			log.Printf("[project] 读取审计运行 %d 的任务 #%d 失败: %v", run.ID, *run.TaskID, err)
			continue
		}
		if t == nil {
			_ = s.m.pg.CodeProjects().FinishAudit(run.ID, run.TaskID, "failed", "审计任务不存在或已删除")
			continue
		}
		switch t.Status {
		case "done":
			taskID := *run.TaskID
			if err := s.m.pg.CodeProjects().MarkAuditedAndReviewed(run.ProjectID, run.TargetCommit, taskID, run.ID); err != nil {
				log.Printf("[project] 审计运行 %d 回写基线失败: %v", run.ID, err)
				continue
			}
			if err := s.m.pg.CodeProjects().FinishAudit(run.ID, run.TaskID, "audited", ""); err != nil {
				log.Printf("[project] 审计运行 %d 标记完成失败: %v", run.ID, err)
			} else {
				log.Printf("[project] 审计运行 %d 完成，项目 %d 基线更新为 %s", run.ID, run.ProjectID, shortCommit(run.TargetCommit))
			}
		case "failed", "timeout":
			_ = s.m.pg.CodeProjects().FinishAudit(run.ID, run.TaskID, "failed", "审计任务结束状态: "+t.Status)
		default:
			// created/running/paused/queued: wait for a terminal state.
		}
	}
}
