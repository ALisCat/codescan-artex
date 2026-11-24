package server

import (
	"context"
	"strconv"
	"sync"
	"testing"
	"time"

	"github.com/Autumn-27/artex/agent"
	pgdb "github.com/Autumn-27/artex/db"
)

func newObservationTestEnv(t *testing.T) (*Server, *Task, *pgdb.DB, int64) {
	t.Helper()
	dsn, _, err := pgdb.DSN()
	if err != nil {
		t.Skip("test postgres not configured")
	}
	pg, err := pgdb.Open(dsn)
	if err != nil {
		t.Fatal(err)
	}
	expID, err := pg.CreateExploration("observation-test", "test report_observation")
	if err != nil {
		pg.Close()
		t.Fatal(err)
	}
	taskID := time.Now().UnixNano()
	task := &Task{
		ID:    strconv.FormatInt(taskID, 10),
		ExpID: expID,
		Store: pg.Exploration(expID),
	}
	s := &Server{
		ctx: context.Background(),
		m:   &Manager{pg: pg, dir: t.TempDir()},
	}
	t.Cleanup(func() {
		_, _ = pg.Exec(`DELETE FROM ca_cells WHERE task_id=$1`, taskID)
		_, _ = pg.Exec(`DELETE FROM explorations WHERE id=$1`, expID)
		pg.Close()
	})
	return s, task, pg, taskID
}

func importObservationTestCell(t *testing.T, pg *pgdb.DB, taskID int64, key, method, url, vuln, origin, status string) {
	t.Helper()
	cell := pgdb.CellInput{
		CellKey:     key,
		VulnClass:   vuln,
		Direction:   "test cell",
		Eligibility: "applicable",
	}
	cell.Endpoint.Method = method
	cell.Endpoint.URL = url
	_, err := pg.Cells().ImportSnapshot(taskID, []pgdb.CellSnapshotInput{{
		Cell: cell, Origin: origin, Status: status,
	}})
	if err != nil {
		t.Fatal(err)
	}
}

func TestRecordObservationOutOfScopeIsDeferred(t *testing.T) {
	s, task, pg, taskID := newObservationTestEnv(t)
	importObservationTestCell(t, pg, taskID, "GET /api/obs/search:authz", "GET", "/api/obs/search", "authz", "delta", "clean")

	result, err := s.recordWorkerObservation(task, agent.ObservationSpec{
		Method: "GET", URL: "/api/obs/export", VulnClass: "hardcoded-credentials",
		Summary: "out-of-scope observation", Reason: "test",
	})
	if err != nil {
		t.Fatal(err)
	}
	if !result.Deferred {
		t.Fatalf("out-of-scope observation must be deferred, got %#v", result)
	}
	if c, err := pg.Cells().Get(taskID, "GET /api/obs/export:hardcoded-credentials"); err != nil {
		t.Fatal(err)
	} else if c != nil {
		t.Fatalf("out-of-scope observation created a matrix cell: %#v", c)
	}
	cells, err := pg.Cells().List(taskID, "")
	if err != nil {
		t.Fatal(err)
	}
	if len(cells) != 1 {
		t.Fatalf("cell count = %d, want 1", len(cells))
	}
}

func TestRecordObservationInScopeCreatesSingleIntent(t *testing.T) {
	s, task, pg, taskID := newObservationTestEnv(t)
	importObservationTestCell(t, pg, taskID, "GET /api/obs/search:authz", "GET", "/api/obs/search", "authz", "delta", "clean")

	result, err := s.recordWorkerObservation(task, agent.ObservationSpec{
		Method: "GET", URL: "/api/obs/search", VulnClass: "hardcoded-credentials",
		Summary: "in-scope observation", Reason: "test",
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.Deferred {
		t.Fatalf("in-scope observation must not be deferred: %#v", result)
	}
	key := "GET /api/obs/search:hardcoded-credentials"
	c, err := pg.Cells().Get(taskID, key)
	if err != nil {
		t.Fatal(err)
	}
	if c == nil {
		t.Fatalf("observation cell %s was not created", key)
	}
	if c.Origin != "observation" {
		t.Fatalf("origin = %q, want observation", c.Origin)
	}
	if c.Status != "dispatched" || c.IntentID == nil {
		t.Fatalf("observation cell not dispatched: status=%q intent=%v", c.Status, c.IntentID)
	}
	var intents int
	if err := pg.QueryRow(`SELECT count(*) FROM exploration_nodes WHERE exploration_id=$1 AND kind='intent'`, task.ExpID).Scan(&intents); err != nil {
		t.Fatal(err)
	}
	if intents != 1 {
		t.Fatalf("intent count = %d, want exactly 1", intents)
	}
}

func TestSeedCellIntentsConcurrentClaimsOnlyOnce(t *testing.T) {
	s, task, pg, taskID := newObservationTestEnv(t)
	importObservationTestCell(t, pg, taskID, "GET /api/obs/concurrent:authz", "GET", "/api/obs/concurrent", "authz", "delta", "pending")

	const workers = 8
	var wg sync.WaitGroup
	errs := make(chan error, workers)
	seeded := make(chan int, workers)
	start := make(chan struct{})
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			n, err := s.seedCellIntents(task, 0)
			if err != nil {
				errs <- err
				return
			}
			seeded <- n
		}()
	}
	close(start)
	wg.Wait()
	close(errs)
	close(seeded)
	for err := range errs {
		t.Fatal(err)
	}
	total := 0
	for n := range seeded {
		total += n
	}
	if total != 1 {
		t.Fatalf("seeded intents = %d, want 1", total)
	}
	var intents int
	if err := pg.QueryRow(`SELECT count(*) FROM exploration_nodes WHERE exploration_id=$1 AND kind='intent'`, task.ExpID).Scan(&intents); err != nil {
		t.Fatal(err)
	}
	if intents != 1 {
		t.Fatalf("intent count = %d, want exactly 1", intents)
	}
	c, err := pg.Cells().Get(taskID, "GET /api/obs/concurrent:authz")
	if err != nil {
		t.Fatal(err)
	}
	if c == nil || c.Status != "dispatched" || c.IntentID == nil {
		t.Fatalf("cell was not dispatched exactly once: %#v", c)
	}
}

func TestCellDisplayNameSupportsObservationTypes(t *testing.T) {
	if got := cellDisplayName("hardcoded-credentials"); got != "硬编码凭据" {
		t.Fatalf("display name = %q", got)
	}
	if got := cellDisplayName("custom-vuln-class"); got != "custom-vuln-class" {
		t.Fatalf("unknown display name should fall back to raw class, got %q", got)
	}
}

func TestObservationAndEngineSeedRaceCreatesOneIntent(t *testing.T) {
	s, task, pg, taskID := newObservationTestEnv(t)
	importObservationTestCell(t, pg, taskID, "GET /api/obs/race:authz", "GET", "/api/obs/race", "authz", "delta", "clean")

	start := make(chan struct{})
	var wg sync.WaitGroup
	errs := make(chan error, 2)
	wg.Add(2)
	go func() {
		defer wg.Done()
		<-start
		_, err := s.recordWorkerObservation(task, agent.ObservationSpec{
			Method: "GET", URL: "/api/obs/race", VulnClass: "hardcoded-credentials",
			Summary: "race observation", Reason: "test",
		})
		if err != nil {
			errs <- err
		}
	}()
	go func() {
		defer wg.Done()
		<-start
		if _, err := s.seedCellIntents(task, 0); err != nil {
			errs <- err
		}
	}()
	close(start)
	wg.Wait()
	close(errs)
	for err := range errs {
		t.Fatal(err)
	}

	var intents int
	if err := pg.QueryRow(`SELECT count(*) FROM exploration_nodes WHERE exploration_id=$1 AND kind='intent'`, task.ExpID).Scan(&intents); err != nil {
		t.Fatal(err)
	}
	if intents != 1 {
		t.Fatalf("intent count = %d, want exactly 1", intents)
	}
}

func TestNewApplicableCellKeys(t *testing.T) {
	mk := func(key, vuln, elig string) pgdb.CellInput {
		c := pgdb.CellInput{CellKey: key, VulnClass: vuln, Eligibility: elig, Direction: "test"}
		c.Endpoint.Method = "GET"
		c.Endpoint.URL = key[:len(key)-len(vuln)-1]
		return c
	}
	body := importCellsBody{Tasks: []pgdb.CellInput{
		mk("GET /api/new:authz", "authz", "applicable"),               // new applicable
		mk("/api/new:xss", "xss", "not_applicable"),                   // new but N/A
		mk("GET /api/base:authz", "authz", "applicable"),              // inherited key
		mk("/api/delta:sql-injection", "sql-injection", "applicable"), // delta
		mk("repo://secrets:secrets", "secrets", "applicable"),         // repo-level new applicable
	}}
	base := map[string]pgdb.Cell{
		"GET /api/base:authz": {CellKey: "GET /api/base:authz"},
	}
	got := newApplicableCellKeys(body, base, []string{"/api/delta:sql-injection"})
	want := map[string]bool{
		"GET /api/new:authz":     true,
		"repo://secrets:secrets": true,
	}
	if len(got) != len(want) {
		t.Fatalf("keys = %#v, want %d", got, len(want))
	}
	for _, key := range got {
		if !want[key] {
			t.Fatalf("unexpected new applicable key %q (all=%#v)", key, got)
		}
	}
}
