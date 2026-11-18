package gitlabsrc

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

func newTestClient(t *testing.T, h http.HandlerFunc) *Client {
	t.Helper()
	srv := httptest.NewServer(h)
	t.Cleanup(srv.Close)
	c, err := New(srv.URL+"/users/sign_in", "glpat-test")
	if err != nil {
		t.Fatal(err)
	}
	if c.BaseURL != strings.TrimRight(srv.URL, "/") {
		t.Fatalf("base = %q, want origin %q", c.BaseURL, srv.URL)
	}
	return c
}

func TestVerifyAndProjectCallsUsePrivateToken(t *testing.T) {
	var sawToken string
	c := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		sawToken = r.Header.Get("PRIVATE-TOKEN")
		switch r.URL.EscapedPath() {
		case "/api/v4/user":
			_, _ = w.Write([]byte(`{"id":7,"username":"codescan-bot","name":"CodeScan Bot"}`))
		case "/api/v4/projects/group%2Fproject", "/api/v4/projects/12":
			_, _ = w.Write([]byte(`{"id":12,"path_with_namespace":"group/project","name":"Project","default_branch":"main","web_url":"https://gitlab.example/group/project"}`))
		case "/api/v4/projects/12/repository/branches/main":
			_, _ = w.Write([]byte(`{"name":"main","commit":{"id":"abcdef123456"}}`))
		case "/api/v4/projects/12/repository/branches":
			_, _ = w.Write([]byte(`[{"name":"main","commit":{"id":"abcdef123456"}},{"name":"test-branch","commit":{"id":"abcdef123456"}}]`))
		case "/api/v4/projects":
			if r.URL.Query().Get("membership") != "true" || r.URL.Query().Get("search") != "clinic" {
				t.Errorf("unexpected query: %s", r.URL.RawQuery)
			}
			_, _ = w.Write([]byte(`[{"id":12,"path_with_namespace":"group/project","name":"Project","default_branch":"main"}]`))
		default:
			t.Errorf("unexpected path %s (escaped %s)", r.URL.Path, r.URL.EscapedPath())
			http.NotFound(w, r)
		}
	})
	ctx := context.Background()
	u, err := c.Verify(ctx)
	if err != nil || u.Username != "codescan-bot" {
		t.Fatalf("verify = %+v, %v", u, err)
	}
	p, err := c.Project(ctx, 0, "group/project")
	if err != nil || p.ID != 12 || p.PathWithNamespace != "group/project" {
		t.Fatalf("project = %+v, %v", p, err)
	}
	if _, err := c.Project(ctx, 12, ""); err != nil {
		t.Fatal(err)
	}
	b, err := c.Branch(ctx, 12, "main")
	if err != nil || b.Commit.ID != "abcdef123456" {
		t.Fatalf("branch = %+v, %v", b, err)
	}
	branches, err := c.ListBranches(ctx, 12)
	if err != nil || len(branches) != 2 || branches[1].Name != "test-branch" {
		t.Fatalf("branches = %+v, %v", branches, err)
	}
	list, err := c.ListProjects(ctx, "clinic", 1, 50)
	if err != nil || len(list) != 1 || list[0].ID != 12 {
		t.Fatalf("list = %+v, %v", list, err)
	}
	if sawToken != "glpat-test" {
		t.Fatalf("PRIVATE-TOKEN = %q", sawToken)
	}
}

func TestUnauthorizedIsReadable(t *testing.T) {
	c := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
	})
	_, err := c.Verify(context.Background())
	if err == nil || !strings.Contains(err.Error(), "Token") {
		t.Fatalf("err = %v", err)
	}
}

func TestNewRejectsBadBaseURL(t *testing.T) {
	for _, raw := range []string{"", "gitlab.example.com", "ftp://gitlab.example.com", "https://user:pass@gitlab.example.com"} {
		if _, err := New(raw, "x"); err == nil {
			t.Fatalf("New(%q) accepted", raw)
		}
	}
}

func TestDownloadArchiveUsesTokenAndPath(t *testing.T) {
	c := newTestClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("PRIVATE-TOKEN") != "glpat-test" {
			t.Errorf("missing token")
		}
		if r.URL.EscapedPath() != "/api/v4/projects/12/repository/archive.zip" {
			t.Errorf("path = %s", r.URL.EscapedPath())
		}
		if r.URL.Query().Get("sha") != "abc123" {
			t.Errorf("sha = %s", r.URL.Query().Get("sha"))
		}
		_, _ = w.Write([]byte("zip-bytes"))
	})
	dst := t.TempDir() + "/archive.zip"
	n, err := c.DownloadArchive(context.Background(), 12, "abc123", dst)
	if err != nil || n != int64(len("zip-bytes")) {
		t.Fatalf("download = %d, %v", n, err)
	}
	b, err := os.ReadFile(dst)
	if err != nil || string(b) != "zip-bytes" {
		t.Fatalf("file = %q, %v", b, err)
	}
}
