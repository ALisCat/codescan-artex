package db

import (
	"encoding/json"
	"fmt"
	"testing"
)

func authzCell(id int64, controller string) Cell {
	hints, _ := json.Marshal(map[string]any{
		"flow": []any{map[string]any{
			"cls": "net.example." + controller,
		}},
	})
	return Cell{
		ID:          id,
		CellKey:     fmt.Sprintf("GET /api/%d:authz", id),
		Method:      "GET",
		EndpointURL: fmt.Sprintf("/api/%d", id),
		VulnClass:   "authz",
		Eligibility: "applicable",
		Priority:    16,
		Hints:       hints,
	}
}

func ssrfCell(id int64, sinkFile string) Cell {
	hints, _ := json.Marshal(map[string]any{
		"sinks": []any{map[string]any{
			"api":  "HttpRequest.post",
			"file": sinkFile,
		}},
	})
	return Cell{
		ID:          id,
		CellKey:     fmt.Sprintf("POST /api/%d:ssrf", id),
		Method:      "POST",
		EndpointURL: fmt.Sprintf("/api/%d", id),
		VulnClass:   "ssrf",
		Eligibility: "applicable",
		Priority:    12,
		Hints:       hints,
	}
}

func TestGroupCellsAggregatesAuthzByController(t *testing.T) {
	cells := make([]Cell, 0, 10)
	for i := 1; i <= 10; i++ {
		cells = append(cells, authzCell(int64(i), "OrderController"))
	}
	groups := GroupCells(cells, 100, 4, true, true)
	if len(groups) != 2 {
		t.Fatalf("expected 2 authz groups, got %d", len(groups))
	}
	if len(groups[0].Cells) != authzAggregatePerGroup {
		t.Fatalf("first group = %d cells, want %d", len(groups[0].Cells), authzAggregatePerGroup)
	}
	if !groups[0].Aggregated || groups[0].AggregateLabel != "OrderController" {
		t.Fatalf("unexpected first group label: %+v", groups[0])
	}
}

func TestGroupCellsAggregatesSSRFBySink(t *testing.T) {
	cells := make([]Cell, 0, 7)
	for i := 1; i <= 7; i++ {
		cells = append(cells, ssrfCell(int64(i), "/src/service/CommonHisImpl.java"))
	}
	groups := GroupCells(cells, 100, 4, true, true)
	if len(groups) != 2 {
		t.Fatalf("expected 2 ssrf groups, got %d", len(groups))
	}
	if got := groups[0].AggregateLabel; got != "HttpRequest.post @ CommonHisImpl.java" {
		t.Fatalf("unexpected ssrf label: %q", got)
	}
}

func TestGroupCellsDisablesAggregation(t *testing.T) {
	cells := make([]Cell, 0, 10)
	for i := 1; i <= 10; i++ {
		cells = append(cells, authzCell(int64(i), "OrderController"))
	}
	groups := GroupCells(cells, 100, 4, false, false)
	// No aggregation means one group per endpoint; this test only has one
	// endpoint per cell, so all 10 groups are separate.
	if len(groups) != 10 {
		t.Fatalf("expected 10 unaggregated groups, got %d", len(groups))
	}
	for _, g := range groups {
		if g.Aggregated {
			t.Fatalf("unexpected aggregated group: %+v", g)
		}
	}
}
