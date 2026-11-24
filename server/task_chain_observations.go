package server

import (
	"encoding/json"
	"net/http"
	"strings"

	"github.com/Autumn-27/artex/db"
)

// taskChainObservations returns deferred worker facts that look like cross-endpoint
// chain risks. This is intentionally separate from the endpoint × vuln matrix:
// chains are follow-up material, not cells that should reopen a completed matrix.
func (s *Server) taskChainObservations(w http.ResponseWriter, r *http.Request) {
	t, ok := s.resolveVisibleTask(currentUser(r), r.PathValue("id"))
	if !ok || t == nil {
		writeErr(w, http.StatusNotFound, "task not found")
		return
	}
	facts, err := t.Store.ListByKind(db.KindFact, 10000)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, err.Error())
		return
	}
	out := make([]*db.Node, 0)
	for _, fact := range facts {
		if isChainObservation(fact.Payload) {
			out = append(out, fact)
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"observations": taskNodeDTOs(out)})
}

func isChainObservation(raw json.RawMessage) bool {
	var payload struct {
		Kind    string `json:"kind"`
		Chain   bool   `json:"chain"`
		Summary string `json:"summary"`
		Detail  string `json:"detail"`
	}
	if len(raw) > 0 {
		_ = json.Unmarshal(raw, &payload)
	}
	if strings.EqualFold(strings.TrimSpace(payload.Kind), "chain") || payload.Chain {
		return true
	}
	text := payload.Summary + "\n" + payload.Detail
	return strings.Contains(text, "链式") || strings.Contains(text, "二阶")
}
