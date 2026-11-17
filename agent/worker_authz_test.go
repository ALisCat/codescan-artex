package agent

import (
	"strings"
	"testing"

	"github.com/Autumn-27/artex/db"
)

func TestMatrixIntentPreludeAuthzModel(t *testing.T) {
	payload := []byte(`{"cases":[{"cell_key":"/api/orders/{id}:authz","vulnclass":"authz","hints":{"authz_model":{"principal":{"var":"user","source":"UserContext.require()","file":"OrderService.java","line":6},"resource":{"type":"Order","identifier":"order","file":"OrderService.java","line":7},"decisions":[{"kind":"ownership","rule":"order.ownerId == user.id","file":"AccessService.java","line":5,"condition":"order.getOwnerId().equals(user.getId())"}],"required":["authentication","ownership"],"coverage":["authentication","ownership"],"gaps":[],"search_policy":{"allow_global_search":false,"search_budget":2,"search_kinds":[],"search_patterns":[]}},"guard_helpers":[{"kind":"ownership","method":"ensureAccess","resolved":true,"call_file":"AccessService.java","call_line":5,"target_file":"AccessService.java","target_line":5}]}}]}`)
	n := &db.Node{Payload: payload}
	got := matrixIntentPrelude(n)
	for _, want := range []string{"授权判定模型", "principal: user", "ownership: order.ownerId == user.id", "gaps    : none", "search  : allow=false budget=2", "helper 1: ownership ensureAccess", "禁止 LS/Write/Edit"} {
		if !strings.Contains(got, want) {
			t.Fatalf("missing %q in prelude:\n%s", want, got)
		}
	}
	if strings.Contains(got, "守卫 1") {
		t.Fatalf("raw guards should be suppressed when model exists:\n%s", got)
	}
}

func TestGateMatrixSearchTools(t *testing.T) {
	base := CodeAuditTools()
	has := func(tools []string, name string) bool {
		for _, n := range tools {
			if n == name {
				return true
			}
		}
		return false
	}
	payload := func(allow bool) []byte {
		if allow {
			return []byte(`{"cases":[{"hints":{"authz_model":{"gaps":[]},"search_policy":{"allow_global_search":true,"search_budget":2}}}]}`)
		}
		return []byte(`{"cases":[{"hints":{"authz_model":{"gaps":[]},"search_policy":{"allow_global_search":false,"search_budget":2}}}]}`)
	}

	var off []string
	for _, tool := range gateMatrixSearchTools(base, &db.Node{Payload: payload(false)}) {
		off = append(off, tool.Name())
	}
	for _, banned := range []string{"Grep", "Glob", "LS", "Write", "Edit"} {
		if has(off, banned) {
			t.Fatalf("allow=false should remove %s, got %v", banned, off)
		}
	}
	if !has(off, "Read") {
		t.Fatalf("allow=false should keep Read, got %v", off)
	}

	var on []string
	for _, tool := range gateMatrixSearchTools(base, &db.Node{Payload: payload(true)}) {
		on = append(on, tool.Name())
	}
	for _, want := range []string{"Grep", "Glob", "Read"} {
		if !has(on, want) {
			t.Fatalf("allow=true should keep %s, got %v", want, on)
		}
	}
	for _, banned := range []string{"LS", "Write", "Edit"} {
		if has(on, banned) {
			t.Fatalf("allow=true should still remove %s, got %v", banned, on)
		}
	}
}

func TestMatrixIntentPreludeAuthnModel(t *testing.T) {
	payload := []byte(`{"cases":[{"cell_key":"/notifyCallBack:authn","vulnclass":"authn","hints":{"authn_model":{"endpoint_kind":"callback","required":["signature","replay_protection"],"decisions":[],"gaps":["signature","replay_protection"],"unknowns":[],"search_policy":{"allow_global_search":true,"search_budget":2,"search_kinds":["signature","replay_protection"],"search_patterns":["checkSign|HMAC","timestamp|nonce"]}}}}]}`)
	n := &db.Node{Payload: payload}
	got := matrixIntentPrelude(n)
	for _, want := range []string{"认证/回调判定模型", "kind    : callback", "gaps    : signature, replay_protection", "search  : allow=true budget=2", "authz_model/authn_model"} {
		if !strings.Contains(got, want) {
			t.Fatalf("missing %q in prelude:\n%s", want, got)
		}
	}
}

func TestGateAuthnSearchTools(t *testing.T) {
	payload := []byte(`{"cases":[{"hints":{"authn_model":{"gaps":[]},"search_policy":{"allow_global_search":false,"search_budget":2}}}]}`)
	var names []string
	for _, tool := range gateMatrixSearchTools(CodeAuditTools(), &db.Node{Payload: payload}) {
		names = append(names, tool.Name())
	}
	for _, banned := range []string{"Grep", "Glob", "LS", "Write", "Edit"} {
		for _, n := range names {
			if n == banned {
				t.Fatalf("authn allow=false should remove %s, got %v", banned, names)
			}
		}
	}
}

func TestManualNotApplicablePreludeAllowsExpansion(t *testing.T) {
	payload := []byte(`{"manual":true,"analyzer_state":"na","cases":[{"cell_key":"/x:authz","vulnclass":"authz","hints":{"flow":[{"name":"detail","file":"X.java","line":10}],"sites":[]}}]}`)
	n := &db.Node{Payload: payload}
	got := matrixIntentPrelude(n)
	for _, want := range []string{"人工审计", "原判定: na", "detail @ X.java:10", "最多 4 次"} {
		if !strings.Contains(got, want) {
			t.Fatalf("missing %q in manual prelude:\n%s", want, got)
		}
	}
	if strings.Contains(got, "只读 flow") {
		t.Fatalf("manual N/A should allow expansion, got:\n%s", got)
	}
	authz, allow, budget := matrixAuthzSearchPolicy(n)
	if !authz || !allow || budget != 4 {
		t.Fatalf("manual search policy = authz=%v allow=%v budget=%d, want true/true/4", authz, allow, budget)
	}
}
