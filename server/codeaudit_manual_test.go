package server

import (
	"encoding/json"
	"testing"

	"github.com/Autumn-27/artex/db"
)

func TestManualCellHintsOnlyCopiesEndpointFlow(t *testing.T) {
	sibling := &db.Cell{Hints: json.RawMessage(`{
		"flow":[{"name":"detail","file":"UserController.java","line":20}],
		"params":["id"],
		"sites":[{"api":"executeQuery","file":"UserDao.java","line":40}],
		"authz_model":{"required":true,"gaps":["owner"]},
		"guards_seen":[{"text":"checkRole","file":"UserController.java","line":22}]
	}`)}
	hints := manualCellHints(sibling)
	var got map[string]any
	if err := json.Unmarshal(hints, &got); err != nil {
		t.Fatalf("invalid hints: %v", err)
	}
	if got["state"] != "manual" || got["analyzer_state"] != "manual" {
		t.Fatalf("state mismatch: %#v", got)
	}
	if _, ok := got["flow"]; !ok {
		t.Fatalf("flow must be copied: %#v", got)
	}
	if _, ok := got["params"]; !ok {
		t.Fatalf("params must be copied: %#v", got)
	}
	for _, forbidden := range []string{"sites", "authz_model", "guards_seen"} {
		if _, ok := got[forbidden]; ok {
			t.Fatalf("%s must not be copied from another vuln type: %#v", forbidden, got)
		}
	}
}

func TestFindEndpointCellPrefersLongestFlow(t *testing.T) {
	cells := []db.Cell{
		{Method: "GET", EndpointURL: "/api/user", Hints: json.RawMessage(`{"flow":[{"name":"a"}]}`)},
		{Method: "GET", EndpointURL: "/api/user", Hints: json.RawMessage(`{"flow":[{"name":"a"},{"name":"b"}]}`)},
		{Method: "POST", EndpointURL: "/api/user", Hints: json.RawMessage(`{"flow":[{"name":"x"},{"name":"y"},{"name":"z"}]}`)},
	}
	got := findEndpointCell(cells, "get", "/api/user")
	if got == nil {
		t.Fatal("expected sibling cell")
	}
	if n := hintFlowCount(got.Hints); n != 2 {
		t.Fatalf("flow count = %d, want 2", n)
	}
}

func TestMergeEndpointHintsKeepsExistingFields(t *testing.T) {
	dst := json.RawMessage(`{"state":"impossible","flow":[],"authz_model":{"required":true}}`)
	sibling := &db.Cell{Hints: json.RawMessage(`{
		"flow":[{"name":"detail","file":"UserController.java","line":20}],
		"params":["id"],
		"sites":[{"api":"executeQuery"}]
	}`)}
	got := mergeEndpointHints(dst, sibling)
	var m map[string]any
	if err := json.Unmarshal(got, &m); err != nil {
		t.Fatalf("invalid hints: %v", err)
	}
	if n := len(m["flow"].([]any)); n != 1 {
		t.Fatalf("flow count = %d, want 1", n)
	}
	if _, ok := m["authz_model"]; !ok {
		t.Fatalf("existing authz_model must be preserved: %#v", m)
	}
	if _, ok := m["sites"]; ok {
		t.Fatalf("sites from sibling must not be copied: %#v", m)
	}
	if _, ok := m["params"]; !ok {
		t.Fatalf("params missing: %#v", m)
	}
}
