package server

import (
	"testing"

	"github.com/Autumn-27/artex/agent"
)

func TestMatrixIntentIsStructured(t *testing.T) {
	cases := []struct {
		name string
		spec agent.IntentSpec
		want bool
	}{
		{"summary only", agent.IntentSpec{Summary: "鉴权与越权链路专项"}, false},
		{"cell keys", agent.IntentSpec{CellKeys: []string{"/api/x:authz"}}, true},
		{"targets", agent.IntentSpec{Targets: []agent.IntentTarget{{Method: "POST", URL: "/api/x", VulnClass: "authz"}}}, true},
		{"repo", agent.IntentSpec{Scope: "repo", Files: []string{"TokenUtil.java"}}, true},
		{"pattern", agent.IntentSpec{Scope: "pattern", Pattern: "MyBatis ${} 插值", Files: []string{"UserMapper.xml"}}, true},
	}
	for _, c := range cases {
		if got := matrixIntentIsStructured(c.spec); got != c.want {
			t.Fatalf("%s: got %v want %v", c.name, got, c.want)
		}
	}
}

func TestMatrixPayloadEndpointCount(t *testing.T) {
	if got := matrixPayloadEndpointCount([]byte(`{"detail":"GET /api/report/appointments clean"}`)); got != 1 {
		t.Fatalf("single endpoint count = %d, want 1", got)
	}
	if got := matrixPayloadEndpointCount([]byte(`{"detail":"/api/a and /api/b"}`)); got != 2 {
		t.Fatalf("multi endpoint count = %d, want 2", got)
	}
}
