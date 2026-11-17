package agent

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/Autumn-27/artex/db"
)

func TestPlannerIntentPreludePatternScope(t *testing.T) {
	payload := []byte(`{
		"summary":"检查同类 MyBatis 语句",
		"scope":"pattern",
		"pattern":"MyBatis ${} 插值",
		"files":["source/src/main/resources/mapper/UserMapper.xml"]
	}`)
	n := &db.Node{Payload: json.RawMessage(payload)}
	got := plannerIntentPrelude(n)
	for _, want := range []string{"范围模式：pattern", "目标模式：MyBatis ${} 插值", "目标文件：source/src/main/resources/mapper/UserMapper.xml"} {
		if !strings.Contains(got, want) {
			t.Fatalf("missing %q in pattern prelude:\n%s", want, got)
		}
	}
}

func TestIntentOriginPayloadScope(t *testing.T) {
	n := &db.Node{Payload: json.RawMessage(`{"scope":"pattern","summary":"x"}`)}
	if got := intentOriginPayloadScope(n); got != "pattern" {
		t.Fatalf("scope = %q, want pattern", got)
	}
}
