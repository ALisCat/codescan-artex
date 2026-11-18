package server

import (
	"context"
	"log"
	"strings"
	"time"
)

const gitlabProjectCheckInterval = 24 * time.Hour

// startGitLabProjectChecker performs the daily, read-only HEAD check. It never
// downloads source and never creates audit tasks; a project is only marked as
// having a new commit so a user can decide whether to start an incremental run.
func (s *Server) startGitLabProjectChecker() {
	if s == nil || s.ctx == nil {
		return
	}
	go func() {
		// Do not race startup or tests. The first check runs shortly after boot,
		// then once per day.
		timer := time.NewTimer(5 * time.Minute)
		defer timer.Stop()
		for {
			select {
			case <-s.ctx.Done():
				return
			case <-timer.C:
				s.checkAllGitLabProjects()
				timer.Reset(gitlabProjectCheckInterval)
			}
		}
	}()
}

func (s *Server) checkAllGitLabProjects() {
	_, token, _, _ := s.gitlabConfig()
	if strings.TrimSpace(token) == "" {
		return
	}
	c, err := s.gitlabClient()
	if err != nil {
		return
	}
	projects, err := s.m.pg.CodeProjects().List()
	if err != nil {
		log.Printf("[gitlab] 每日检查读取项目失败: %v", err)
		return
	}
	for _, p := range projects {
		select {
		case <-s.ctx.Done():
			return
		default:
		}
		branch := projectBranch(&p)
		ctx, cancel := context.WithTimeout(s.ctx, 25*time.Second)
		b, err := c.Branch(ctx, p.GitLabProjectID, branch)
		cancel()
		if err != nil {
			_ = s.m.pg.CodeProjects().UpdateCheck(p.ID, "", err.Error())
			log.Printf("[gitlab] 检查项目 %s 失败: %v", p.Path, err)
			continue
		}
		head := ""
		if b != nil {
			head = b.Commit.ID
		}
		if err := s.m.pg.CodeProjects().UpdateCheck(p.ID, head, ""); err != nil {
			log.Printf("[gitlab] 保存项目 %s 检查结果失败: %v", p.Path, err)
			continue
		}
		if head != "" && head != p.LastAuditedCommit {
			log.Printf("[gitlab] 项目 %s 目标分支有新提交: %s → %s", p.Path, shortCommit(p.LastAuditedCommit), shortCommit(head))
		}
	}
}

func shortCommit(commit string) string {
	if commit == "" {
		return "—"
	}
	if len(commit) > 8 {
		return commit[:8]
	}
	return commit
}
