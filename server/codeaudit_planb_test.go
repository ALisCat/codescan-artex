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
	}
	for _, c := range cases {
		if got := matrixIntentIsStructured(c.spec); got != c.want {
			t.Fatalf("%s: got %v want %v", c.name, got, c.want)
		}
	}
}
