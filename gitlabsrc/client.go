// Package gitlabsrc is the minimal GitLab API client used by the project module.
//
// It is intentionally narrow: either the administrator configured a GitLab
// origin, or no request is made. The client never accepts a project-controlled
// URL, so the SSRF surface is limited to the configured host.
package gitlabsrc

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

type Client struct {
	BaseURL string
	Token   string
	HC      *http.Client
}

type User struct {
	ID       int64  `json:"id"`
	Username string `json:"username"`
	Name     string `json:"name"`
}

type Project struct {
	ID                int64  `json:"id"`
	PathWithNamespace string `json:"path_with_namespace"`
	Name              string `json:"name"`
	DefaultBranch     string `json:"default_branch"`
	WebURL            string `json:"web_url"`
	HTTPURLToRepo     string `json:"http_url_to_repo"`
	LastActivityAt    string `json:"last_activity_at"`
}

type Branch struct {
	Name   string `json:"name"`
	Commit struct {
		ID string `json:"id"`
	} `json:"commit"`
}

func New(baseURL, token string) (*Client, error) {
	baseURL = strings.TrimSpace(baseURL)
	if baseURL == "" {
		return nil, fmt.Errorf("GitLab 地址不能为空")
	}
	u, err := url.Parse(baseURL)
	if err != nil || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return nil, fmt.Errorf("GitLab 地址不合法")
	}
	if u.Scheme != "https" && u.Scheme != "http" {
		return nil, fmt.Errorf("GitLab 地址只支持 http/https")
	}
	origin := u.Scheme + "://" + strings.ToLower(u.Host)
	tr := http.DefaultTransport.(*http.Transport).Clone()
	tr.Proxy = nil
	hc := &http.Client{
		Transport: tr,
		Timeout:   25 * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if len(via) >= 5 {
				return fmt.Errorf("GitLab 重定向次数过多")
			}
			if !sameOrigin(req.URL, origin) {
				return fmt.Errorf("GitLab 重定向到了非配置主机")
			}
			return nil
		},
	}
	return &Client{BaseURL: origin, Token: strings.TrimSpace(token), HC: hc}, nil
}

func sameOrigin(u *url.URL, origin string) bool {
	o, err := url.Parse(origin)
	if err != nil {
		return false
	}
	return strings.EqualFold(u.Scheme, o.Scheme) && strings.EqualFold(u.Host, o.Host)
}

// DownloadArchive streams the fixed commit archive to dst. The normal API client
// has a short timeout, but an archive body can legitimately take minutes; use a
// context-bound client with the same origin/redirect policy instead.
func (c *Client) DownloadArchive(ctx context.Context, projectID int64, sha, dst string) (int64, error) {
	if projectID <= 0 || strings.TrimSpace(sha) == "" {
		return 0, fmt.Errorf("GitLab 项目 ID 和 commit 不能为空")
	}
	u := fmt.Sprintf("%s/api/v4/projects/%d/repository/archive.zip?sha=%s", c.BaseURL, projectID, url.QueryEscape(sha))
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return 0, fmt.Errorf("构造 GitLab 归档请求失败")
	}
	req.Header.Set("User-Agent", "CodeScan")
	req.Header.Set("Accept", "application/zip")
	if c.Token != "" {
		req.Header.Set("PRIVATE-TOKEN", c.Token)
	}
	hc := &http.Client{Transport: c.HC.Transport, CheckRedirect: c.HC.CheckRedirect}
	resp, err := hc.Do(req)
	if err != nil {
		return 0, fmt.Errorf("下载 GitLab 源码失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
		return 0, fmt.Errorf("GitLab Token 无权限或已失效（HTTP %d）", resp.StatusCode)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return 0, fmt.Errorf("下载 GitLab 源码失败（HTTP %d）: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	f, err := os.Create(dst)
	if err != nil {
		return 0, fmt.Errorf("创建源码临时文件失败: %w", err)
	}
	n, copyErr := io.Copy(f, resp.Body)
	closeErr := f.Close()
	if copyErr != nil {
		return n, fmt.Errorf("下载 GitLab 源码中断: %w", copyErr)
	}
	if closeErr != nil {
		return n, fmt.Errorf("写入源码临时文件失败: %w", closeErr)
	}
	if n == 0 {
		return 0, fmt.Errorf("GitLab 归档为空")
	}
	return n, nil
}

type CompareCommit struct {
	ID         string `json:"id"`
	ShortID    string `json:"short_id"`
	Title      string `json:"title"`
	AuthorName string `json:"author_name"`
	CreatedAt  string `json:"created_at"`
}

type CompareDiff struct {
	OldPath     string `json:"old_path"`
	NewPath     string `json:"new_path"`
	NewFile     bool   `json:"new_file"`
	RenamedFile bool   `json:"renamed_file"`
	DeletedFile bool   `json:"deleted_file"`
	Diff        string `json:"diff"`
}

type Compare struct {
	Commit         CompareCommit   `json:"commit"`
	Commits        []CompareCommit `json:"commits"`
	Diffs          []CompareDiff   `json:"diffs"`
	CompareTimeout bool            `json:"compare_timeout"`
	CompareSameRef bool            `json:"compare_same_ref"`
}

// Compare returns GitLab's unified diff between two commits. The caller must
// treat compare_timeout as an incomplete result, not as "no changes".
func (c *Client) Compare(ctx context.Context, projectID int64, from, to string) (*Compare, error) {
	if projectID <= 0 || strings.TrimSpace(from) == "" || strings.TrimSpace(to) == "" {
		return nil, fmt.Errorf("GitLab compare 参数不完整")
	}
	var out Compare
	path := fmt.Sprintf("/projects/%d/repository/compare?from=%s&to=%s", projectID,
		url.QueryEscape(from), url.QueryEscape(to))
	if err := c.request(ctx, http.MethodGet, path, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// RawFile downloads one text file at a fixed ref. It is used only for changed
// Controller files during change preview; a hard cap keeps a pathological file
// from turning into a memory problem.
func (c *Client) RawFile(ctx context.Context, projectID int64, filePath, ref string) ([]byte, error) {
	if projectID <= 0 || strings.TrimSpace(filePath) == "" || strings.TrimSpace(ref) == "" {
		return nil, fmt.Errorf("GitLab raw 参数不完整")
	}
	u := fmt.Sprintf("%s/api/v4/projects/%d/repository/files/%s/raw?ref=%s", c.BaseURL, projectID,
		url.PathEscape(filePath), url.QueryEscape(ref))
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, fmt.Errorf("构造 GitLab raw 请求失败")
	}
	req.Header.Set("User-Agent", "CodeScan")
	if c.Token != "" {
		req.Header.Set("PRIVATE-TOKEN", c.Token)
	}
	resp, err := c.HC.Do(req)
	if err != nil {
		return nil, fmt.Errorf("读取 GitLab 文件失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("GitLab 文件不存在或当前 Token 不可见")
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("读取 GitLab 文件失败（HTTP %d）", resp.StatusCode)
	}
	const limit = 2 << 20
	b, err := io.ReadAll(io.LimitReader(resp.Body, limit+1))
	if err != nil {
		return nil, fmt.Errorf("读取 GitLab 文件失败: %w", err)
	}
	if len(b) > limit {
		return nil, fmt.Errorf("文件超过预览上限（2 MiB）")
	}
	return b, nil
}

func (c *Client) request(ctx context.Context, method, path string, out any) error {
	if c == nil {
		return fmt.Errorf("GitLab 客户端未初始化")
	}
	u := c.BaseURL + "/api/v4" + path
	req, err := http.NewRequestWithContext(ctx, method, u, nil)
	if err != nil {
		return fmt.Errorf("构造 GitLab 请求失败")
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "CodeScan")
	if c.Token != "" {
		req.Header.Set("PRIVATE-TOKEN", c.Token)
	}
	resp, err := c.HC.Do(req)
	if err != nil {
		return fmt.Errorf("请求 GitLab 失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
		return fmt.Errorf("GitLab Token 无权限或已失效（HTTP %d）", resp.StatusCode)
	}
	if resp.StatusCode == http.StatusNotFound {
		return fmt.Errorf("GitLab 项目不存在或当前 Token 不可见")
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return fmt.Errorf("GitLab 返回 HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	if out == nil {
		return nil
	}
	if err := json.NewDecoder(io.LimitReader(resp.Body, 8<<20)).Decode(out); err != nil {
		return fmt.Errorf("解析 GitLab 响应失败: %w", err)
	}
	return nil
}

func (c *Client) Verify(ctx context.Context) (*User, error) {
	var u User
	if err := c.request(ctx, http.MethodGet, "/user", &u); err != nil {
		return nil, err
	}
	return &u, nil
}

func (c *Client) ListProjects(ctx context.Context, search string, page, perPage int) ([]Project, error) {
	if page <= 0 {
		page = 1
	}
	if perPage <= 0 || perPage > 100 {
		perPage = 50
	}
	q := url.Values{}
	q.Set("membership", "true")
	q.Set("simple", "true")
	q.Set("archived", "false")
	q.Set("per_page", fmt.Sprintf("%d", perPage))
	q.Set("page", fmt.Sprintf("%d", page))
	if strings.TrimSpace(search) != "" {
		q.Set("search", strings.TrimSpace(search))
	}
	var out []Project
	if err := c.request(ctx, http.MethodGet, "/projects?"+q.Encode(), &out); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) Project(ctx context.Context, projectID int64, path string) (*Project, error) {
	ref := strings.TrimSpace(path)
	if projectID > 0 {
		ref = fmt.Sprintf("%d", projectID)
	}
	if ref == "" {
		return nil, fmt.Errorf("GitLab 项目 ID 或路径不能为空")
	}
	var out Project
	if err := c.request(ctx, http.MethodGet, "/projects/"+url.PathEscape(ref), &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// ListBranches returns up to 100 branches. Projects with more than 100 branches
// can still be used by typing a branch name; the selector shows the first page.
func (c *Client) ListBranches(ctx context.Context, projectID int64) ([]Branch, error) {
	if projectID <= 0 {
		return nil, fmt.Errorf("GitLab 项目 ID 不能为空")
	}
	var out []Branch
	if err := c.request(ctx, http.MethodGet,
		fmt.Sprintf("/projects/%d/repository/branches?per_page=100", projectID), &out); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) Branch(ctx context.Context, projectID int64, ref string) (*Branch, error) {
	if projectID <= 0 || strings.TrimSpace(ref) == "" {
		return nil, fmt.Errorf("GitLab 项目 ID 和分支不能为空")
	}
	// GitLab accepts URL-encoded branch names, including group/feature names.
	var out Branch
	if err := c.request(ctx, http.MethodGet,
		fmt.Sprintf("/projects/%d/repository/branches/%s", projectID, url.PathEscape(ref)), &out); err != nil {
		return nil, err
	}
	return &out, nil
}
