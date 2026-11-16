package agent

import (
	"strings"
	"testing"

	"github.com/Autumn-27/artex/db"
)

func TestMatrixIntentPreludeAuthzModel(t *testing.T) {
	payload := []byte(`{"cases":[{"cell_key":"/api/orders/{id}:authz","vulnclass":"authz","hints":{"authz_model":{"principal":{"var":"user","source":"UserContext.require()","file":"OrderService.java","line":6},"resource":{"type":"Order","identifier":"order","file":"OrderService.java","line":7},"decisions":[{"kind":"ownership","rule":"order.ownerId == user.id","file":"AccessService.java","line":5,"condition":"order.getOwnerId().equals(user.getId())"}],"required":["authentication","ownership"],"coverage":["authentication","ownership"],"gaps":[]},"guard_helpers":[{"kind":"ownership","method":"ensureAccess","resolved":true,"call_file":"AccessService.java","call_line":5,"target_file":"AccessService.java","target_line":5}]}}]}`)
	n := &db.Node{Payload: payload}
	got := matrixIntentPrelude(n)
	for _, want := range []string{"授权判定模型", "principal: user", "ownership: order.ownerId == user.id", "gaps    : none", "helper 1: ownership ensureAccess"} {
		if !strings.Contains(got, want) {
			t.Fatalf("missing %q in prelude:\n%s", want, got)
		}
	}
	if strings.Contains(got, "守卫 1") {
		t.Fatalf("raw guards should be suppressed when model exists:\n%s", got)
	}
}
