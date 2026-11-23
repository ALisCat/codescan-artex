package server

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestAccessProfileBlock(t *testing.T) {
	if got := accessProfileBlock(nil); got != "" {
		t.Fatalf("empty profile block = %q, want empty", got)
	}
	raw, _ := json.Marshal(projectAccessProfile{
		MultiEnd: "yes", ManagementScope: "all", ClientScope: "self",
		SharedManagement: "yes", Notes: "shared schedule",
	})
	got := accessProfileBlock(raw)
	for _, want := range []string{"多端系统：是", "管理端数据范围：允许访问全部数据", "客户端数据范围：只能访问本人数据", "客户端可访问的管理端接口：有", "scope=all"} {
		if !strings.Contains(got, want) {
			t.Fatalf("profile block missing %q:\n%s", want, got)
		}
	}
}

func TestNormalizeAccessProfile(t *testing.T) {
	in := projectAccessProfile{MultiEnd: "yes", ManagementScope: "all", ClientScope: "self", SharedManagement: "no"}
	out, err := normalizeAccessProfile(in)
	if err != nil || out.ManagementScope != "all" {
		t.Fatalf("normalize = %+v, %v", out, err)
	}
	in.ManagementScope = "everything"
	if _, err := normalizeAccessProfile(in); err == nil {
		t.Fatal("invalid management scope accepted")
	}
}

func TestAdvancedAccessProfile(t *testing.T) {
	raw := json.RawMessage(`{"mode":"advanced","multi_end":"yes","management_scope":"unknown","client_scope":"unknown","shared_management":"unknown","advanced":{"roles":{"DOCTOR":{"patient":{"read":"all"}}}}}`)
	p, err := normalizeAccessProfile(parseAccessProfile(raw))
	if err != nil {
		t.Fatal(err)
	}
	if p.Mode != "advanced" {
		t.Fatalf("mode = %q", p.Mode)
	}
	block := accessProfileBlock(raw)
	if !strings.Contains(block, "精细模式") || !strings.Contains(block, `"DOCTOR"`) {
		t.Fatalf("advanced block missing rules:\n%s", block)
	}
}
