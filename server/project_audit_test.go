package server

import "testing"

func TestGitLabArchiveWrapperUsesProjectSlug(t *testing.T) {
	cases := map[string]string{
		"group/demo":     "demo-",
		"group/sub/demo": "demo-",
		"/group/demo/":   "demo-",
		"demo":           "demo-",
		"":               "",
	}
	for in, want := range cases {
		if got := gitlabArchiveWrapper(in); got != want {
			t.Fatalf("gitlabArchiveWrapper(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestNormalizeGitLabBaseURLStripsWebPath(t *testing.T) {
	got, err := normalizeGitLabBaseURL("https://gitlab.example.com/users/sign_in")
	if err != nil {
		t.Fatal(err)
	}
	if got != "https://gitlab.example.com" {
		t.Fatalf("base = %q", got)
	}
	if got, err := normalizeGitLabBaseURL(""); err != nil || got != "" {
		t.Fatalf("empty base = %q, %v", got, err)
	}
	for _, raw := range []string{"gitlab.example.com", "ftp://gitlab.example.com", "https://u:p@gitlab.example.com"} {
		if _, err := normalizeGitLabBaseURL(raw); err == nil {
			t.Fatalf("normalize(%q) accepted", raw)
		}
	}
}
