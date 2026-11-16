package agent

// 二开：submit_cell_verdict 的守卫单测（不依赖 LLM / DB）。
//
// 覆盖两个行为：
//   1. verdict=confirmed 但本次运行还没 report_finding → 拒绝，并提示先登记漏洞
//   2. confirmed 且已 report_finding → 正常回写矩阵格子

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	actool "github.com/Autumn-27/norma/tool"
)

func flattenResult(r actool.Result) string {
	var b strings.Builder
	for _, c := range r.Content {
		b.WriteString(c.Text)
	}
	return b.String()
}

func TestSubmitCellVerdictConfirmedRequiresFinding(t *testing.T) {
	ts := NewToolSet(nil, "test-worker")
	var recorded string
	ts.SetCellVerdict(func(cellKey, verdict, reason string, evidence json.RawMessage) error {
		recorded = cellKey + "=" + verdict
		return nil
	})
	tool := ts.submitCellVerdict()

	in := []byte(`{"cell_key":"13:command-exec","verdict":"confirmed","evidence":"Rce.java:31"}`)
	res, err := tool.Call(context.Background(), in, nil)
	if err != nil {
		t.Fatalf("Call 返回 err: %v", err)
	}
	if !res.IsError {
		t.Fatalf("未登记 finding 时 confirmed 应被拒绝，实际通过")
	}
	if !strings.Contains(flattenResult(res), "report_finding") {
		t.Fatalf("拒绝信息应提示 report_finding，实际: %s", flattenResult(res))
	}
	if recorded != "" {
		t.Fatalf("被拒绝时不应回调回写，实际: %s", recorded)
	}

	// 模拟 worker 已经调用过 report_finding
	ts.writes.Findings = 1
	res, err = tool.Call(context.Background(), in, nil)
	if err != nil {
		t.Fatalf("Call 返回 err: %v", err)
	}
	if res.IsError {
		t.Fatalf("已登记 finding 后 confirmed 应通过，实际: %s", flattenResult(res))
	}
	if recorded != "13:command-exec=confirmed" {
		t.Fatalf("回写回调未按预期触发: %q", recorded)
	}
}

func TestSubmitCellVerdictCleanRequiresReason(t *testing.T) {
	ts := NewToolSet(nil, "test-worker")
	ts.SetCellVerdict(func(cellKey, verdict, reason string, evidence json.RawMessage) error { return nil })
	tool := ts.submitCellVerdict()

	res, err := tool.Call(context.Background(), []byte(`{"cell_key":"1:x","verdict":"clean"}`), nil)
	if err != nil {
		t.Fatalf("Call 返回 err: %v", err)
	}
	if !res.IsError {
		t.Fatalf("clean 无正向证据应被拒绝")
	}
	res, err = tool.Call(context.Background(), []byte(`{"cell_key":"1:x","verdict":"clean","reason":"L98 有后缀白名单"}`), nil)
	if err != nil {
		t.Fatalf("Call 返回 err: %v", err)
	}
	if res.IsError {
		t.Fatalf("clean 带证据应通过，实际: %s", flattenResult(res))
	}
}
