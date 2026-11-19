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

	"github.com/Autumn-27/artex/gitlabsrc"
)

type changeHunk struct {
	OldStart int    `json:"old_start"`
	OldLines int    `json:"old_lines"`
	NewStart int    `json:"new_start"`
	NewLines int    `json:"new_lines"`
	Header   string `json:"header,omitempty"`
}

type changeEndpoint struct {
	Method     string `json:"method"`
	Path       string `json:"path"`
	File       string `json:"file"`
	Line       int    `json:"line"`
	Confidence string `json:"confidence"`
}

type changeFile struct {
	OldPath     string           `json:"old_path"`
	NewPath     string           `json:"new_path"`
	Path        string           `json:"path"`
	Status      string           `json:"status"`
	Additions   int              `json:"additions"`
	Deletions   int              `json:"deletions"`
	Hunks       []changeHunk     `json:"hunks"`
	Diff        string           `json:"diff,omitempty"`
	Endpoints   []changeEndpoint `json:"endpoints"`
	DiffOmitted bool             `json:"diff_omitted,omitempty"`
}

type changeSummary struct {
	Commits      int `json:"commits"`
	FilesChanged int `json:"files_changed"`
	Additions    int `json:"additions"`
	Deletions    int `json:"deletions"`
}

type changePreview struct {
	Available         bool                      `json:"available"`
	NeedsFull         bool                      `json:"needs_full"`
	NoChanges         bool                      `json:"no_changes"`
	BaseCommit        string                    `json:"base_commit"`
	TargetCommit      string                    `json:"target_commit"`
	Branch            string                    `json:"branch"`
	ReviewedCommit    string                    `json:"reviewed_commit"`
	ReviewBaseCommit  string                    `json:"review_base_commit"`
	ReviewSameAsAudit bool                      `json:"review_same_as_audit"`
	Commits           []gitlabsrc.CompareCommit `json:"commits"`
	ReviewCommits     []gitlabsrc.CompareCommit `json:"review_commits"`
	Files             []changeFile              `json:"files"`
	Endpoints         []changeEndpoint          `json:"endpoints"`
	FilesChanged      int                       `json:"files_changed"`
	Additions         int                       `json:"additions"`
	Deletions         int                       `json:"deletions"`
	AuditGap          changeSummary             `json:"audit_gap"`
	ReviewSummary     changeSummary             `json:"review_summary"`
	Warnings          []string                  `json:"warnings"`
	DiffTruncated     bool                      `json:"diff_truncated"`
	CompareTimeout    bool                      `json:"compare_timeout"`
}

var (
	diffHunkRE      = regexp.MustCompile(`^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@`)
	springMapRE     = regexp.MustCompile(`@(RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping)\b`)
	javaStringRE    = regexp.MustCompile(`"([^"]*)"`)
	requestMethodRE = regexp.MustCompile(`RequestMethod\.([A-Z]+)`)
)

const (
	maxPreviewFiles     = 200
	maxPreviewDiffBytes = 2 << 20
	maxPreviewRawFiles  = 24
)

func (s *Server) projectChangePreview(w http.ResponseWriter, r *http.Request) {
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
	branch := projectBranch(p)
	out := changePreview{
		BaseCommit:       strings.TrimSpace(p.LastAuditedCommit),
		Branch:           branch,
		ReviewedCommit:   strings.TrimSpace(p.LastReviewedCommit),
		ReviewBaseCommit: strings.TrimSpace(p.LastReviewedCommit),
		Commits:          []gitlabsrc.CompareCommit{},
		ReviewCommits:    []gitlabsrc.CompareCommit{},
		Files:            []changeFile{},
		Endpoints:        []changeEndpoint{},
		Warnings:         []string{},
		Available:        true,
	}
	if out.BaseCommit == "" {
		out.NeedsFull = true
		if out.ReviewBaseCommit == "" {
			out.ReviewBaseCommit = out.BaseCommit
		}
		out.Warnings = append(out.Warnings, "还没有成功审计基线，请先完成一次全量审计。")
		writeJSON(w, 200, out)
		return
	}
	if out.ReviewBaseCommit == "" {
		out.ReviewBaseCommit = out.BaseCommit
		out.ReviewSameAsAudit = true
	}
	c, err := s.gitlabClient()
	if err != nil {
		writeErr(w, 400, err.Error())
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 60*time.Second)
	defer cancel()
	b, err := c.Branch(ctx, p.GitLabProjectID, branch)
	if err != nil {
		writeErr(w, 502, "读取项目分支失败："+err.Error())
		return
	}
	target := strings.TrimSpace(b.Commit.ID)
	out.TargetCommit = target
	if target == "" {
		writeErr(w, 502, "GitLab 返回的分支 commit 为空")
		return
	}
	if target == out.BaseCommit {
		out.NoChanges = true
		out.Warnings = append(out.Warnings, "目标分支没有新提交，无需增量分析。")
		writeJSON(w, 200, out)
		return
	}
	cmp, err := c.Compare(ctx, p.GitLabProjectID, out.BaseCommit, target)
	if err != nil {
		writeJSON(w, 200, map[string]any{
			"available": true, "needs_full": true,
			"base_commit": out.BaseCommit, "target_commit": target, "branch": branch,
			"error": "compare 失败，建议重新全量审计：" + err.Error(),
		})
		return
	}
	out.Commits = cmp.Commits
	if out.Commits == nil {
		out.Commits = []gitlabsrc.CompareCommit{}
	}
	out.CompareTimeout = cmp.CompareTimeout
	if cmp.CompareTimeout {
		out.Warnings = append(out.Warnings, "GitLab compare 超时，结果可能不完整，建议全量审计。")
	}
	rawBudget := maxPreviewRawFiles
	diffBudget := maxPreviewDiffBytes
	for i, d := range cmp.Diffs {
		if i >= maxPreviewFiles {
			out.DiffTruncated = true
			out.Warnings = append(out.Warnings, fmt.Sprintf("变更文件超过 %d 个，仅展示前 %d 个。", maxPreviewFiles, maxPreviewFiles))
			break
		}
		f := changeFile{
			OldPath:   d.OldPath,
			NewPath:   d.NewPath,
			Path:      d.NewPath,
			Status:    "modified",
			Hunks:     []changeHunk{},
			Endpoints: []changeEndpoint{},
		}
		switch {
		case d.NewFile:
			f.Status = "added"
		case d.DeletedFile:
			f.Status = "deleted"
			f.Path = d.OldPath
		case d.RenamedFile:
			f.Status = "renamed"
		}
		if f.Path == "" {
			f.Path = d.OldPath
		}
		f.Additions, f.Deletions, f.Hunks = parseDiffStats(d.Diff)
		if diffBudget > 0 && len(d.Diff) <= diffBudget {
			f.Diff = d.Diff
			diffBudget -= len(d.Diff)
		} else if d.Diff != "" {
			f.DiffOmitted = true
			out.DiffTruncated = true
		}
		if rawBudget > 0 && strings.HasSuffix(strings.ToLower(f.Path), ".java") {
			rawPath := f.Path
			ref := target
			if f.Status == "deleted" {
				rawPath = d.OldPath
				ref = out.BaseCommit
			}
			raw, rawErr := c.RawFile(ctx, p.GitLabProjectID, rawPath, ref)
			if rawErr == nil {
				f.Endpoints = parseSpringEndpoints(raw, f.Path)
				if f.Endpoints == nil {
					f.Endpoints = []changeEndpoint{}
				}
				rawBudget--
			} else {
				out.Warnings = append(out.Warnings, fmt.Sprintf("未能读取 %s 做接口映射：%s", f.Path, rawErr.Error()))
			}
		}
		out.Additions += f.Additions
		out.Deletions += f.Deletions
		out.Files = append(out.Files, f)
		out.Endpoints = append(out.Endpoints, f.Endpoints...)
	}
	out.FilesChanged = len(out.Files)
	if len(out.Files) > 0 && len(out.Endpoints) == 0 {
		out.Warnings = append(out.Warnings, "未从变更文件中识别到 Controller 接口；请结合文件列表人工判断影响面。")
	}
	if len(out.Files) == 0 {
		out.Warnings = append(out.Warnings, "compare 没有返回文件变更。")
		if len(out.Commits) > 0 {
			out.Warnings = append(out.Warnings, "区间内存在提交，但最终文件 diff 为空；可能只是中间提交被回滚或仅修改了元数据，审计仍以最终源码为准。")
		}
	}
	out.AuditGap = changeSummary{
		Commits: len(out.Commits), FilesChanged: out.FilesChanged,
		Additions: out.Additions, Deletions: out.Deletions,
	}
	if out.ReviewBaseCommit == out.BaseCommit {
		out.ReviewSameAsAudit = true
		out.ReviewSummary = out.AuditGap
		out.ReviewCommits = out.Commits
	} else if out.ReviewBaseCommit != target {
		rcmp, rerr := c.Compare(ctx, p.GitLabProjectID, out.ReviewBaseCommit, target)
		if rerr != nil {
			out.Warnings = append(out.Warnings, "自上次已阅的 compare 失败："+rerr.Error())
			out.ReviewSummary = out.AuditGap
			out.ReviewCommits = out.Commits
		} else {
			rAdd, rDel := 0, 0
			for _, d := range rcmp.Diffs {
				a, del, _ := parseDiffStats(d.Diff)
				rAdd += a
				rDel += del
			}
			out.ReviewSummary = changeSummary{
				Commits: len(rcmp.Commits), FilesChanged: len(rcmp.Diffs),
				Additions: rAdd, Deletions: rDel,
			}
			out.ReviewCommits = rcmp.Commits
		}
	}
	writeJSON(w, 200, out)
}

func parseDiffStats(diff string) (int, int, []changeHunk) {
	adds, dels := 0, 0
	hunks := []changeHunk{}
	for _, line := range strings.Split(diff, "\n") {
		if m := diffHunkRE.FindStringSubmatch(line); m != nil {
			oldStart, _ := strconv.Atoi(m[1])
			oldLines := 1
			if m[2] != "" {
				oldLines, _ = strconv.Atoi(m[2])
			}
			newStart, _ := strconv.Atoi(m[3])
			newLines := 1
			if m[4] != "" {
				newLines, _ = strconv.Atoi(m[4])
			}
			hunks = append(hunks, changeHunk{
				OldStart: oldStart, OldLines: oldLines,
				NewStart: newStart, NewLines: newLines, Header: line,
			})
			continue
		}
		if strings.HasPrefix(line, "+++") || strings.HasPrefix(line, "---") {
			continue
		}
		if strings.HasPrefix(line, "+") {
			adds++
		} else if strings.HasPrefix(line, "-") {
			dels++
		}
	}
	return adds, dels, hunks
}

func normalizeEndpointPath(base, value string) string {
	base = strings.TrimSpace(base)
	value = strings.TrimSpace(value)
	if value == "" {
		value = ""
	}
	p := strings.TrimRight(base, "/") + "/" + strings.TrimLeft(value, "/")
	if p == "" {
		return "/"
	}
	if !strings.HasPrefix(p, "/") {
		p = "/" + p
	}
	return p
}

// parseSpringEndpoints is a deliberately small annotation mapper. It is only a
// preview aid: controller annotations are direct evidence; service/XML changes
// remain candidate files and are not guessed into endpoints.
func parseSpringEndpoints(src []byte, file string) []changeEndpoint {
	lines := strings.Split(string(src), "\n")
	classLine := -1
	for i, l := range lines {
		if strings.Contains(l, "class ") || strings.Contains(l, "interface ") {
			classLine = i
			break
		}
	}
	classBase := ""
	classBaseLine := -1
	for i, l := range lines {
		if classLine >= 0 && i >= classLine {
			break
		}
		if springMapRE.MatchString(l) && strings.Contains(l, "RequestMapping") {
			if vals := javaStringRE.FindAllStringSubmatch(l, -1); len(vals) > 0 {
				classBase = vals[0][1]
				classBaseLine = i
				break
			}
		}
	}
	seen := map[string]bool{}
	var out []changeEndpoint
	for i, line := range lines {
		m := springMapRE.FindStringSubmatch(line)
		if m == nil || i == classBaseLine {
			continue
		}
		ann := m[1]
		value := ""
		if vals := javaStringRE.FindAllStringSubmatch(line, -1); len(vals) > 0 {
			value = vals[0][1]
		}
		method := ""
		if rm := requestMethodRE.FindStringSubmatch(line); len(rm) > 1 {
			method = rm[1]
		}
		if ann == "RequestMapping" {
			if method == "" {
				method = "GET"
			}
		} else {
			switch ann {
			case "GetMapping":
				method = "GET"
			case "PostMapping":
				method = "POST"
			case "PutMapping":
				method = "PUT"
			case "DeleteMapping":
				method = "DELETE"
			case "PatchMapping":
				method = "PATCH"
			}
		}
		p := normalizeEndpointPath(classBase, value)
		key := method + " " + p
		if seen[key] {
			continue
		}
		seen[key] = true
		out = append(out, changeEndpoint{
			Method: method, Path: p, File: file, Line: i + 1, Confidence: "direct",
		})
	}
	return out
}

// POST /api/projects/{id}/review marks a commit as reviewed without moving the
// audit baseline. It is explicitly not a security verdict.
func (s *Server) reviewProject(w http.ResponseWriter, r *http.Request) {
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
		Commit string `json:"commit"`
		Note   string `json:"note"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErr(w, 400, "请求格式不正确")
		return
	}
	note := strings.TrimSpace(req.Note)
	if len([]rune(note)) > 2000 {
		writeErr(w, 400, "已阅说明不能超过 2000 字")
		return
	}
	c, err := s.gitlabClient()
	if err != nil {
		writeErr(w, 400, err.Error())
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()
	b, err := c.Branch(ctx, p.GitLabProjectID, projectBranch(p))
	if err != nil {
		writeErr(w, 502, "读取项目分支失败："+err.Error())
		return
	}
	head := strings.TrimSpace(b.Commit.ID)
	if head == "" {
		writeErr(w, 502, "GitLab 返回的分支 commit 为空")
		return
	}
	if req.Commit != "" && strings.TrimSpace(req.Commit) != head {
		writeErr(w, 409, "目标分支已更新，请重新预览后再标记已阅")
		return
	}
	var by *int64
	if u := currentUser(r); u != nil {
		by = &u.ID
	}
	if err := s.m.pg.CodeProjects().MarkReviewed(id, head, by, note); err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	out, _ := s.m.pg.CodeProjects().Get(id)
	writeJSON(w, 200, out)
}
