package server

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/Autumn-27/artex/db"
	"github.com/Autumn-27/artex/gitlabsrc"
)

// GitLab 连接是系统级配置：一个地址 + 一个 service account PAT。
// 项目模块后续的源码下载、compare、每日检查都从这里取凭据。
const (
	settingGitLabBaseURL    = "gitlab_base_url"
	settingGitLabToken      = "gitlab_token"
	settingGitLabUser       = "gitlab_verified_user"
	settingGitLabVerifiedAt = "gitlab_verified_at"
)

var gitlabProjectPathRE = regexp.MustCompile(`^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+$`)

func (s *Server) gitlabConfig() (baseURL, token, verifiedUser, verifiedAt string) {
	baseURL, _, _ = s.m.pg.GetSetting(settingGitLabBaseURL)
	baseURL = strings.TrimSpace(baseURL)
	token, _, _ = s.m.pg.GetSetting(settingGitLabToken)
	token = strings.TrimSpace(token)
	verifiedUser, _, _ = s.m.pg.GetSetting(settingGitLabUser)
	verifiedAt, _, _ = s.m.pg.GetSetting(settingGitLabVerifiedAt)
	return
}

func tokenHint(token string) string {
	token = strings.TrimSpace(token)
	if len(token) <= 8 {
		if token == "" {
			return ""
		}
		return "已配置"
	}
	return "…" + token[len(token)-4:]
}

func normalizeGitLabBaseURL(raw string) (string, error) {
	// Empty means "not configured". It is intentionally allowed so an admin can
	// remove a previously stored address without having to edit the database.
	if strings.TrimSpace(raw) == "" {
		return "", nil
	}
	c, err := gitlabsrc.New(raw, "")
	if err != nil {
		return "", err
	}
	return c.BaseURL, nil
}

func (s *Server) gitlabClient() (*gitlabsrc.Client, error) {
	baseURL, token, _, _ := s.gitlabConfig()
	if strings.TrimSpace(baseURL) == "" {
		return nil, fmt.Errorf("尚未配置 GitLab 地址")
	}
	if strings.TrimSpace(token) == "" {
		return nil, fmt.Errorf("尚未配置 GitLab Token")
	}
	return gitlabsrc.New(baseURL, token)
}

func (s *Server) gitlabSettingsPayload() map[string]any {
	baseURL, token, verifiedUser, verifiedAt := s.gitlabConfig()
	return map[string]any{
		"gitlab_base_url":      baseURL,
		"gitlab_token_set":     strings.TrimSpace(token) != "",
		"gitlab_token_hint":    tokenHint(token),
		"gitlab_verified_user": verifiedUser,
		"gitlab_verified_at":   verifiedAt,
		"gitlab_configured":    strings.TrimSpace(baseURL) != "" && strings.TrimSpace(token) != "",
	}
}

// testGitLab verifies a token against /api/v4/user. It deliberately tests the
// values in the form first, then falls back to stored values, so an admin can
// validate a new token before saving it.
func (s *Server) testGitLab(w http.ResponseWriter, r *http.Request) {
	var req struct {
		BaseURL string `json:"gitlab_base_url"`
		Token   string `json:"gitlab_token"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, 400, err.Error())
		return
	}
	baseURL, storedToken, _, _ := s.gitlabConfig()
	if strings.TrimSpace(req.BaseURL) != "" {
		baseURL = req.BaseURL
	}
	token := storedToken
	if strings.TrimSpace(req.Token) != "" {
		token = req.Token
	}
	if strings.TrimSpace(baseURL) == "" {
		writeJSON(w, 200, map[string]any{"ok": false, "error": "尚未配置 GitLab 地址"})
		return
	}
	baseURL, err := normalizeGitLabBaseURL(baseURL)
	if err != nil {
		writeJSON(w, 200, map[string]any{"ok": false, "error": err.Error()})
		return
	}
	if strings.TrimSpace(token) == "" {
		writeJSON(w, 200, map[string]any{"ok": false, "error": "尚未配置 GitLab Token"})
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 25*time.Second)
	defer cancel()
	c, err := gitlabsrc.New(baseURL, token)
	if err != nil {
		writeJSON(w, 200, map[string]any{"ok": false, "error": err.Error()})
		return
	}
	u, err := c.Verify(ctx)
	if err != nil {
		writeJSON(w, 200, map[string]any{"ok": false, "error": err.Error()})
		return
	}
	// Remember the identity of the last successful verification. This is not a
	// secret and makes the settings page useful after a restart.
	_ = s.m.pg.SetSetting(settingGitLabUser, u.Username)
	_ = s.m.pg.SetSetting(settingGitLabVerifiedAt, time.Now().UTC().Format(time.RFC3339))
	writeJSON(w, 200, map[string]any{
		"ok": true, "base_url": baseURL, "username": u.Username, "name": u.Name, "id": u.ID,
	})
}

func (s *Server) gitlabListProjects(w http.ResponseWriter, r *http.Request) {
	c, err := s.gitlabClient()
	if err != nil {
		writeErr(w, 400, err.Error())
		return
	}
	page := 1
	if n, err := strconv.Atoi(r.URL.Query().Get("page")); err == nil && n > 0 {
		page = n
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	projects, err := c.ListProjects(ctx, r.URL.Query().Get("q"), page, 50)
	if err != nil {
		writeErr(w, 502, err.Error())
		return
	}
	writeJSON(w, 200, map[string]any{"projects": projects, "page": page})
}

// projectBranch is the single branch a project tracks. Legacy rows have an
// empty tracked_branch and fall back to the GitLab default branch.
func projectBranch(p *db.CodeProject) string {
	if p == nil {
		return ""
	}
	if b := strings.TrimSpace(p.TrackedBranch); b != "" {
		return b
	}
	if b := strings.TrimSpace(p.DefaultBranch); b != "" {
		return b
	}
	return "main"
}

func (s *Server) gitlabLookupProject(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimSpace(strings.TrimSuffix(r.URL.Query().Get("path"), ".git"))
	if !gitlabProjectPathRE.MatchString(path) || strings.Contains(path, "://") || strings.Contains(path, "@") || strings.Contains(path, "..") {
		writeErr(w, 400, "项目路径格式应为 group/project 或 group/subgroup/project")
		return
	}
	c, err := s.gitlabClient()
	if err != nil {
		writeErr(w, 400, err.Error())
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	gp, err := c.Project(ctx, 0, path)
	if err != nil {
		writeErr(w, 502, err.Error())
		return
	}
	writeJSON(w, 200, map[string]any{"project": gp})
}

func (s *Server) gitlabListBranches(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil || id <= 0 {
		writeErr(w, 400, "GitLab 项目 ID 不合法")
		return
	}
	c, err := s.gitlabClient()
	if err != nil {
		writeErr(w, 400, err.Error())
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 90*time.Second)
	defer cancel()
	branches, err := c.ListBranches(ctx, id)
	if err != nil {
		writeErr(w, 502, err.Error())
		return
	}
	writeJSON(w, 200, map[string]any{"branches": branches})
}

func (s *Server) listProjects(w http.ResponseWriter, r *http.Request) {
	page, _ := strconv.Atoi(r.URL.Query().Get("page"))
	size, _ := strconv.Atoi(r.URL.Query().Get("size"))
	projects, total, err := s.m.pg.CodeProjects().ListPage(
		r.URL.Query().Get("q"), r.URL.Query().Get("status"), r.URL.Query().Get("sort"), page, size,
	)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	if page <= 0 {
		page = 1
	}
	if size <= 0 || size > 100 {
		size = 20
	}
	writeJSON(w, 200, map[string]any{"projects": projects, "total": total, "page": page, "size": size})
}

func (s *Server) getProject(w http.ResponseWriter, r *http.Request) {
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
	writeJSON(w, 200, p)
}

func projectPathFromGitLab(p *gitlabsrc.Project) string {
	if p == nil {
		return ""
	}
	if strings.TrimSpace(p.PathWithNamespace) != "" {
		return strings.TrimSpace(p.PathWithNamespace)
	}
	return strings.TrimSpace(p.Name)
}

func (s *Server) createProject(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Path            string `json:"path"`
		Name            string `json:"name"`
		Branch          string `json:"branch"`
		GitLabProjectID int64  `json:"gitlab_project_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, 400, err.Error())
		return
	}
	req.Path = strings.TrimSpace(strings.TrimSuffix(req.Path, ".git"))
	if req.GitLabProjectID <= 0 && !gitlabProjectPathRE.MatchString(req.Path) {
		writeErr(w, 400, "项目路径格式应为 group/project 或 group/subgroup/project")
		return
	}
	// A path from the UI is a repo path, not a URL. Refuse anything with a
	// scheme/@ so an editor cannot turn this into an arbitrary HTTP fetch.
	if strings.Contains(req.Path, "://") || strings.Contains(req.Path, "@") || strings.Contains(req.Path, "..") {
		writeErr(w, 400, "项目路径不合法")
		return
	}
	c, err := s.gitlabClient()
	if err != nil {
		writeErr(w, 400, err.Error())
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	gp, err := c.Project(ctx, req.GitLabProjectID, req.Path)
	if err != nil {
		writeErr(w, 502, err.Error())
		return
	}
	path := projectPathFromGitLab(gp)
	if path == "" {
		writeErr(w, 502, "GitLab 返回的项目路径为空")
		return
	}
	branch := strings.TrimSpace(req.Branch)
	if branch == "" {
		branch = strings.TrimSpace(gp.DefaultBranch)
	}
	if branch == "" {
		branch = "main"
	}
	b, err := c.Branch(ctx, gp.ID, branch)
	if err != nil {
		writeErr(w, 400, fmt.Sprintf("分支 %s 不存在或当前 Token 不可见：%s", branch, err.Error()))
		return
	}
	head := ""
	if b != nil {
		head = b.Commit.ID
	}
	name := strings.TrimSpace(req.Name)
	if name == "" {
		name = fmt.Sprintf("%s · %s", gp.Name, branch)
	}
	u := currentUser(r)
	var createdBy *int64
	if u != nil {
		createdBy = &u.ID
	}
	p, err := s.m.pg.CodeProjects().Create(db.CodeProject{
		Name:            name,
		Path:            path,
		GitLabProjectID: gp.ID,
		WebURL:          gp.WebURL,
		DefaultBranch:   gp.DefaultBranch,
		TrackedBranch:   branch,
		LastSeenCommit:  head,
		Status:          "active",
		CreatedBy:       createdBy,
	})
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	writeJSON(w, 201, p)
}

func (s *Server) checkProject(w http.ResponseWriter, r *http.Request) {
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
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	branch := projectBranch(p)
	b, err := c.Branch(ctx, p.GitLabProjectID, branch)
	if err != nil {
		_ = s.m.pg.CodeProjects().UpdateCheck(id, "", err.Error())
		writeErr(w, 502, err.Error())
		return
	}
	if err := s.m.pg.CodeProjects().UpdateCheck(id, b.Commit.ID, ""); err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	out, _ := s.m.pg.CodeProjects().Get(id)
	writeJSON(w, 200, out)
}

func (s *Server) deleteProject(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil || id <= 0 {
		writeErr(w, 400, "项目 ID 不合法")
		return
	}
	if err := s.m.pg.CodeProjects().Delete(id); err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	writeJSON(w, 200, map[string]any{"ok": true})
}
