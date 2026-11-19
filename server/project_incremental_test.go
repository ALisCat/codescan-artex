package server

import (
	"encoding/json"
	"testing"

	"github.com/Autumn-27/artex/db"
)

func TestSemanticChangedRangesIgnoresCommentOnly(t *testing.T) {
	javaDiff := "@@ -68,3 +68,5 @@\n }\n+\n+// multi-commit preview controller marker\n"
	if got := semanticChangedRanges("src/AppointmentController.java", javaDiff); len(got) != 0 {
		t.Fatalf("comment-only Java diff produced ranges: %#v", got)
	}
	xmlDiff := "@@ -90,3 +90,5 @@\n </mapper>\n+\n+<!-- multi-commit preview mapper marker -->\n"
	if got := semanticChangedRanges("src/main/resources/mapper/AppointmentMapper.xml", xmlDiff); len(got) != 0 {
		t.Fatalf("comment-only XML diff produced ranges: %#v", got)
	}
}

func TestSelectDeltaCellsUsesMethodLineRanges(t *testing.T) {
	hints, _ := json.Marshal(map[string]any{
		"flow": []map[string]any{{"file": "src/AppointmentController.java", "line": 10, "end": 20}},
	})
	body := importCellsBody{Tasks: []db.CellInput{{
		CellKey: "/api/appointment/list:authz", VulnClass: "authz", Eligibility: "applicable",
		Hints: hints, Endpoint: struct {
			Method  string `json:"method"`
			URL     string `json:"url"`
			AssetID int64  `json:"asset_id"`
		}{Method: "GET", URL: "/api/appointment/list"},
	}}}
	hit := selectDeltaCells(body, incrementalDelta{ChangedRanges: map[string][]lineRange{
		"src/appointmentcontroller.java": {{Start: 12, End: 12}},
	}})
	if len(hit.Keys) != 1 || hit.Keys[0] != "/api/appointment/list:authz" {
		t.Fatalf("method change did not select cell: %#v", hit)
	}
	comment := selectDeltaCells(body, incrementalDelta{ChangedRanges: map[string][]lineRange{
		"src/appointmentcontroller.java": {{Start: 30, End: 30}},
	}})
	if len(comment.Keys) != 0 || len(comment.Gaps) != 0 {
		t.Fatalf("out-of-method change should not select or gap: %#v", comment)
	}
}

func TestSelectDeltaCellsReportsNewEndpointGap(t *testing.T) {
	hints, _ := json.Marshal(map[string]any{
		"flow": []map[string]any{{"file": "src/MultiCommitTestController.java", "line": 10, "end": 14}},
	})
	body := importCellsBody{Tasks: []db.CellInput{{
		CellKey: "/api/multi/ping:authz", VulnClass: "authz", Eligibility: "not_applicable",
		Hints: hints, Endpoint: struct {
			Method  string `json:"method"`
			URL     string `json:"url"`
			AssetID int64  `json:"asset_id"`
		}{Method: "GET", URL: "/api/multi/ping"},
	}}}
	got := selectDeltaCells(body, incrementalDelta{ChangedRanges: map[string][]lineRange{
		"src/multicommittestcontroller.java": {{Start: 11, End: 11}},
	}})
	if len(got.Keys) != 0 {
		t.Fatalf("N/A cell must not be audited: %#v", got)
	}
	if len(got.Gaps) != 1 || got.Gaps[0] != "GET /api/multi/ping" {
		t.Fatalf("N/A endpoint should be reported as gap: %#v", got)
	}
}
