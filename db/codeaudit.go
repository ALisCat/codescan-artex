package db

// 二开：审计矩阵（ca_cells）的存储层。
//
// 设计要点：
//   - 矩阵只负责"派方向"，不产出 confirmed/clean；结论由 worker 通过
//     submit_cell_verdict 回写。
//   - 一行 = 一个 (task, endpoint, vulnclass) 格子。
//   - status 是覆盖度的唯一来源：pending 与 clean 必须能区分。

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"time"
)

// Cell 是矩阵的一个格子。
type Cell struct {
	ID           int64           `json:"id"`
	TaskID       int64           `json:"task_id"`
	CellKey      string          `json:"cell_key"`
	EndpointURL  string          `json:"endpoint_url"`
	Method       string          `json:"method"`
	VulnClass    string          `json:"vulnclass"`
	Eligibility  string          `json:"eligibility"`
	Priority     int             `json:"priority"`
	Bucket       string          `json:"bucket"`
	Direction    string          `json:"direction"`
	Checklist    json.RawMessage `json:"checklist"`
	Hints        json.RawMessage `json:"hints"`
	HintsNote    string          `json:"hints_note"`
	Reason       string          `json:"reason"`
	Trace        json.RawMessage `json:"trace"`
	Status       string          `json:"status"`
	Verdict      string          `json:"verdict,omitempty"`
	Evidence     json.RawMessage `json:"evidence,omitempty"`
	IntentID     *int64          `json:"intent_id,omitempty"`
	Attempts     int             `json:"attempts"`
	LastError    string          `json:"last_error,omitempty"`
	Origin       string          `json:"origin"`
	SourceTaskID *int64          `json:"source_task_id,omitempty"`
	CreatedAt    time.Time       `json:"created_at"`
	UpdatedAt    time.Time       `json:"updated_at"`
}

// CellInput 是导入时的一项（对应生成器 tasks.json 的一条）。
type CellInput struct {
	CellKey     string          `json:"task_id"`
	Direction   string          `json:"direction"`
	VulnClass   string          `json:"vulnclass"`
	Priority    int             `json:"priority"`
	Bucket      string          `json:"bucket"`
	Checklist   []string        `json:"checklist"`
	Hints       json.RawMessage `json:"hints"`
	HintsNote   string          `json:"hints_note"`
	Eligibility string          `json:"eligibility"`
	Hold        bool            `json:"hold"` // true: 保留在矩阵可见，但不派单（低置信默认不派）
	Reason      string          `json:"reason"`
	Trace       json.RawMessage `json:"trace"`
	Endpoint    struct {
		Method  string `json:"method"`
		URL     string `json:"url"`
		AssetID int64  `json:"asset_id"`
	} `json:"endpoint"`
}

// CellSnapshotInput is a target-matrix row with an explicit provenance and
// settled status. Incremental tasks use it to merge base conclusions into the
// complete target matrix without re-dispatching inherited cells.
type CellSnapshotInput struct {
	Cell         CellInput
	Origin       string
	SourceTaskID *int64
	Status       string
	Verdict      string
	Evidence     json.RawMessage
}

// CellStore 是 ca_cells 的访问入口。
type CellStore struct {
	db *DB
}

// Cells 返回矩阵存储。
func (d *DB) Cells() *CellStore { return &CellStore{db: d} }

// Import 幂等导入一批格子。已存在的按 cell_key 更新方向/优先级/线索，
// 不覆盖已有的 status/verdict（避免重复导入冲掉 worker 结论）。
func (s *CellStore) Import(taskID int64, items []CellInput) (int, error) {
	if taskID <= 0 {
		return 0, fmt.Errorf("task_id 无效")
	}
	n := 0
	for _, it := range items {
		if it.CellKey == "" || it.VulnClass == "" {
			continue
		}
		elig := it.Eligibility
		if elig == "" {
			elig = "applicable"
			if it.Bucket == "P3" {
				elig = "needs_review"
			}
		}
		status := "pending"
		switch elig {
		case "not_applicable":
			status = "na"
		case "unverified":
			status = "unverified"
		}
		if it.Hold {
			status = "hold"
		}
		direction := it.Direction
		if direction == "" {
			direction = "不适用：" + it.Reason
		}
		trace := it.Trace
		if len(trace) == 0 || string(trace) == "null" {
			trace = json.RawMessage(`[]`)
		}
		checklist, _ := json.Marshal(it.Checklist)
		hints := it.Hints
		if len(hints) == 0 || string(hints) == "null" {
			hints = json.RawMessage(`{}`)
		}
		_, err := s.db.Exec(`
INSERT INTO ca_cells (task_id, cell_key, endpoint_url, method, vulnclass, eligibility,
                      priority, bucket, direction, checklist, hints, hints_note,
                      status, reason, trace)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12,$13,$14,$15::jsonb)
ON CONFLICT (task_id, cell_key) DO UPDATE SET
    endpoint_url = EXCLUDED.endpoint_url,
    method       = EXCLUDED.method,
    vulnclass    = EXCLUDED.vulnclass,
    eligibility  = EXCLUDED.eligibility,
    priority     = EXCLUDED.priority,
    bucket       = EXCLUDED.bucket,
    direction    = EXCLUDED.direction,
    checklist    = EXCLUDED.checklist,
    hints        = EXCLUDED.hints,
    hints_note   = EXCLUDED.hints_note,
    reason       = EXCLUDED.reason,
    trace        = EXCLUDED.trace,
    updated_at   = now()`,
			taskID, it.CellKey, it.Endpoint.URL, it.Endpoint.Method, it.VulnClass, elig,
			it.Priority, it.Bucket, direction, checklist, hints, it.HintsNote,
			status, it.Reason, trace)
		if err != nil {
			return n, err
		}
		n++
	}
	return n, nil
}

// ImportSnapshot inserts target-matrix rows with provenance and settled
// status. Unlike Import, it preserves status/verdict/evidence for inherited
// cells and does not seed intents.
func (s *CellStore) ImportSnapshot(taskID int64, items []CellSnapshotInput) (int, error) {
	if taskID <= 0 {
		return 0, fmt.Errorf("task_id 无效")
	}
	n := 0
	for _, item := range items {
		it := item.Cell
		if it.CellKey == "" || it.VulnClass == "" {
			continue
		}
		elig := it.Eligibility
		if elig == "" {
			elig = "applicable"
			if it.Bucket == "P3" {
				elig = "needs_review"
			}
		}
		status := item.Status
		if status == "" {
			status = "pending"
			switch elig {
			case "not_applicable":
				status = "na"
			case "unverified":
				status = "unverified"
			}
			if it.Hold {
				status = "hold"
			}
		}
		direction := it.Direction
		if direction == "" {
			direction = "不适用：" + it.Reason
		}
		trace := it.Trace
		if len(trace) == 0 || string(trace) == "null" {
			trace = json.RawMessage(`[]`)
		}
		checklist, _ := json.Marshal(it.Checklist)
		hints := it.Hints
		if len(hints) == 0 || string(hints) == "null" {
			hints = json.RawMessage(`{}`)
		}
		evidence := item.Evidence
		if len(evidence) == 0 || string(evidence) == "null" {
			evidence = nil
		}
		origin := item.Origin
		if origin == "" {
			origin = "matrix"
		}
		var verdict any
		if item.Verdict != "" {
			verdict = item.Verdict
		}
		_, err := s.db.Exec(`
INSERT INTO ca_cells (task_id, cell_key, endpoint_url, method, vulnclass, eligibility,
                      priority, bucket, direction, checklist, hints, hints_note,
                      status, verdict, evidence, reason, trace, origin, source_task_id)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11::jsonb,$12,$13,$14,$15::jsonb,$16,$17::jsonb,$18,$19)
ON CONFLICT (task_id, cell_key) DO UPDATE SET
    endpoint_url = EXCLUDED.endpoint_url,
    method       = EXCLUDED.method,
    vulnclass    = EXCLUDED.vulnclass,
    eligibility  = EXCLUDED.eligibility,
    priority     = EXCLUDED.priority,
    bucket       = EXCLUDED.bucket,
    direction    = EXCLUDED.direction,
    checklist    = EXCLUDED.checklist,
    hints        = EXCLUDED.hints,
    hints_note   = EXCLUDED.hints_note,
    reason       = EXCLUDED.reason,
    trace        = EXCLUDED.trace,
    origin       = EXCLUDED.origin,
    source_task_id = EXCLUDED.source_task_id,
    updated_at   = now()`,
			taskID, it.CellKey, it.Endpoint.URL, it.Endpoint.Method, it.VulnClass, elig,
			it.Priority, it.Bucket, direction, checklist, hints, it.HintsNote,
			status, verdict, evidence, it.Reason, trace, origin, item.SourceTaskID)
		if err != nil {
			return n, err
		}
		n++
	}
	return n, nil
}

// PendingUndispatched 取还没建过意图的格子（按优先级）。
func (s *CellStore) PendingUndispatched(taskID int64, limit int) ([]Cell, error) {
	if limit <= 0 {
		limit = 50
	}
	rows, err := s.db.Query(`
SELECT id, task_id, cell_key, endpoint_url, method, vulnclass, eligibility,
       priority, bucket, direction, checklist, hints, hints_note, reason, trace,
       status, COALESCE(verdict,''), evidence, intent_id, attempts, last_error, created_at, updated_at,
       COALESCE(origin,'matrix'), source_task_id
FROM ca_cells
WHERE task_id=$1 AND status='pending' AND intent_id IS NULL
ORDER BY priority DESC, id ASC
LIMIT $2`, taskID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanCells(rows)
}

// Get 取单个格子。
func (s *CellStore) Get(taskID int64, cellKey string) (*Cell, error) {
	rows, err := s.db.Query(`
SELECT id, task_id, cell_key, endpoint_url, method, vulnclass, eligibility,
       priority, bucket, direction, checklist, hints, hints_note, reason, trace,
       status, COALESCE(verdict,''), evidence, intent_id, attempts, last_error, created_at, updated_at,
       COALESCE(origin,'matrix'), source_task_id
FROM ca_cells WHERE task_id=$1 AND cell_key=$2 LIMIT 1`, taskID, cellKey)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	cells, err := scanCells(rows)
	if err != nil {
		return nil, err
	}
	if len(cells) == 0 {
		return nil, nil
	}
	return &cells[0], nil
}

// UpdateHints 只更新线索，不改 status/verdict。用于人工审计前给旧格子补接口 flow。
func (s *CellStore) UpdateHints(taskID int64, cellKey string, hints json.RawMessage) error {
	if len(hints) == 0 || string(hints) == "null" {
		return nil
	}
	_, err := s.db.Exec(`
UPDATE ca_cells SET hints=$3::jsonb, updated_at=now()
WHERE task_id=$1 AND cell_key=$2`, taskID, cellKey, hints)
	return err
}

// MarkManual 把格子标记为人工发起的审计（status=dispatched，绑定新 intent）。
// 原判定为 not_applicable 的格子改为 applicable，使其结论进入覆盖度统计。
// 已 dispatched 的格子不覆盖（返回 rows=0，由调用方报冲突）。
func (s *CellStore) MarkManual(taskID int64, cellKey string, intentID int64, direction, reason string) (int64, error) {
	res, err := s.db.Exec(`
UPDATE ca_cells
SET status='dispatched',
    intent_id=$3,
    eligibility=CASE WHEN eligibility IN ('not_applicable','unverified') THEN 'applicable' ELSE eligibility END,
    direction=$4,
    reason=$5,
    attempts=0,
    last_error='',
    updated_at=now()
WHERE task_id=$1 AND cell_key=$2 AND status <> 'dispatched'`, taskID, cellKey, intentID, direction, reason)
	if err != nil {
		return 0, err
	}
	return res.RowsAffected()
}

// List 按状态列出格子（status 为空则全部）。
func (s *CellStore) List(taskID int64, status string) ([]Cell, error) {
	q := `
SELECT id, task_id, cell_key, endpoint_url, method, vulnclass, eligibility,
       priority, bucket, direction, checklist, hints, hints_note, reason, trace,
       status, COALESCE(verdict,''), evidence, intent_id, attempts, last_error, created_at, updated_at,
       COALESCE(origin,'matrix'), source_task_id
FROM ca_cells WHERE task_id=$1`
	args := []any{taskID}
	if status != "" {
		q += ` AND status=$2`
		args = append(args, status)
	}
	q += ` ORDER BY priority DESC, id ASC`
	rows, err := s.db.Query(q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanCells(rows)
}

func scanCells(rows *sql.Rows) ([]Cell, error) {
	var out []Cell
	for rows.Next() {
		var (
			c                Cell
			checklist, hints []byte
			trace, evidence  []byte
			verdict          sql.NullString
			intentID         sql.NullInt64
			sourceTaskID     sql.NullInt64
		)
		if err := rows.Scan(&c.ID, &c.TaskID, &c.CellKey, &c.EndpointURL, &c.Method,
			&c.VulnClass, &c.Eligibility, &c.Priority, &c.Bucket, &c.Direction,
			&checklist, &hints, &c.HintsNote, &c.Reason, &trace,
			&c.Status, &verdict, &evidence, &intentID, &c.Attempts, &c.LastError, &c.CreatedAt, &c.UpdatedAt,
			&c.Origin, &sourceTaskID); err != nil {
			return nil, err
		}
		if len(checklist) == 0 {
			checklist = []byte("[]")
		}
		if len(hints) == 0 {
			hints = []byte("{}")
		}
		if len(trace) == 0 {
			trace = []byte("[]")
		}
		c.Checklist = json.RawMessage(checklist)
		c.Hints = json.RawMessage(hints)
		c.Trace = json.RawMessage(trace)
		if len(evidence) > 0 {
			c.Evidence = json.RawMessage(evidence)
		}
		if verdict.Valid {
			c.Verdict = verdict.String
		}
		if intentID.Valid {
			v := intentID.Int64
			c.IntentID = &v
		}
		if sourceTaskID.Valid {
			v := sourceTaskID.Int64
			c.SourceTaskID = &v
		}
		out = append(out, c)
	}
	return out, rows.Err()
}

// MarkDispatched 记录格子已经生成对应意图。
func (s *CellStore) MarkDispatched(cellID, intentID int64) error {
	_, err := s.db.Exec(`
UPDATE ca_cells SET status='dispatched', intent_id=$2, updated_at=now()
WHERE id=$1 AND status='pending'`, cellID, intentID)
	return err
}

// SubmitVerdict 回写 worker 结论。
func (s *CellStore) SubmitVerdict(taskID int64, cellKey, verdict, reason string, evidence json.RawMessage) error {
	switch verdict {
	case "confirmed", "clean", "needs_more":
	default:
		return fmt.Errorf("verdict 必须是 confirmed/clean/needs_more")
	}
	if len(evidence) == 0 || string(evidence) == "null" {
		evidence = json.RawMessage(`{}`)
	}
	res, err := s.db.Exec(`
UPDATE ca_cells SET status=$3, verdict=$3,
       evidence = COALESCE($4::jsonb, evidence),
       reason = CASE WHEN $5 = '' THEN reason ELSE $5 END,
       updated_at=now()
WHERE task_id=$1 AND cell_key=$2`, taskID, cellKey, verdict, evidence, reason)
	if err != nil {
		return err
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return fmt.Errorf("格子不存在: %s", cellKey)
	}
	return nil
}

// CellStats 返回按状态/类型的统计。
type CellStats struct {
	Total           int            `json:"total"`
	ApplicableTotal int            `json:"applicable_total"`
	NA              int            `json:"not_applicable"`
	Unverified      int            `json:"unverified"`
	Hold            int            `json:"hold"`
	ByStatus        map[string]int `json:"by_status"`
	ByVulnClass     map[string]int `json:"by_vulnclass"`
	CoveragePct     float64        `json:"coverage_pct"`
}

func (s *CellStore) Stats(taskID int64) (*CellStats, error) {
	st := &CellStats{ByStatus: map[string]int{}, ByVulnClass: map[string]int{}}
	rows, err := s.db.Query(`SELECT status, vulnclass, eligibility, count(*) FROM ca_cells WHERE task_id=$1 GROUP BY 1,2,3`, taskID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	done := 0
	for rows.Next() {
		var status, vuln, elig string
		var n int
		if err := rows.Scan(&status, &vuln, &elig, &n); err != nil {
			return nil, err
		}
		st.Total += n
		st.ByStatus[status] += n
		st.ByVulnClass[vuln] += n
		if elig == "not_applicable" {
			st.NA += n
			continue
		}
		if elig == "unverified" {
			st.Unverified += n
			continue
		}
		if status == "hold" {
			st.Hold += n
			continue
		}
		st.ApplicableTotal += n
		if status == "confirmed" || status == "clean" {
			done += n
		}
	}
	if st.ApplicableTotal > 0 {
		st.CoveragePct = float64(done) / float64(st.ApplicableTotal) * 100
	}
	return st, rows.Err()
}

// CellGroup 是同一接口的待办格子集合（派发时合并成一个意图，避免同一处代码被
// 多个类型各报一次 finding）。
type CellGroup struct {
	EndpointURL string
	Method      string
	Cells       []Cell
}

// PendingGroups 把待办格子按 (method,url) 分组；每组最多 maxPerGroup 个、
// 最多返回 maxGroups 组。
func (s *CellStore) PendingGroups(taskID int64, maxGroups, maxPerGroup int) ([]CellGroup, error) {
	if maxGroups <= 0 {
		maxGroups = 20
	}
	if maxPerGroup <= 0 {
		maxPerGroup = 4
	}
	rows, err := s.db.Query(`
SELECT id, task_id, cell_key, endpoint_url, method, vulnclass, eligibility,
       priority, bucket, direction, checklist, hints, hints_note, reason, trace,
       status, COALESCE(verdict,''), evidence, intent_id, attempts, last_error, created_at, updated_at,
       COALESCE(origin,'matrix'), source_task_id
FROM ca_cells
WHERE task_id=$1 AND status='pending' AND intent_id IS NULL
ORDER BY priority DESC, id ASC`, taskID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	cells, err := scanCells(rows)
	if err != nil {
		return nil, err
	}
	order := []string{}
	idx := map[string]*CellGroup{}
	for _, c := range cells {
		key := c.Method + " " + c.EndpointURL
		if maxPerGroup == 1 {
			// 单格派发：每个格子独立成组，即使同一接口有多个类型
			key = "cell:" + c.CellKey
		}
		g := idx[key]
		if g == nil {
			if len(order) >= maxGroups*3 { // 先收集，后面再截断
				break
			}
			g = &CellGroup{EndpointURL: c.EndpointURL, Method: c.Method}
			idx[key] = g
			order = append(order, key)
		}
		if len(g.Cells) >= maxPerGroup {
			continue
		}
		g.Cells = append(g.Cells, c)
	}
	out := make([]CellGroup, 0, maxGroups)
	for _, k := range order {
		if g := idx[k]; g != nil && len(g.Cells) > 0 {
			out = append(out, *g)
			if len(out) >= maxGroups {
				break
			}
		}
	}
	return out, nil
}

// Requeue 把 dispatched 的格子退回 pending（意图 blocked/exhausted/stopped 时调用）。
// 已有结论的格子（confirmed/clean/needs_more）不受影响。attempts 达到 3 时置 failed。
func (s *CellStore) Requeue(taskID int64, cellKey, cause string) error {
	_, err := s.db.Exec(`
UPDATE ca_cells
SET status = CASE WHEN attempts + 1 >= 3 THEN 'failed' ELSE 'pending' END,
    attempts = attempts + 1,
    last_error = $3,
    intent_id = NULL,
    updated_at = now()
WHERE task_id=$1 AND cell_key=$2 AND status='dispatched'`, taskID, cellKey, cause)
	return err
}

// Unfinished 返回仍未了结的格子数（pending + dispatched）。
func (s *CellStore) Unfinished(taskID int64) (int, error) {
	var n int
	err := s.db.QueryRow(`SELECT count(*) FROM ca_cells WHERE task_id=$1 AND status IN ('pending','dispatched')`, taskID).Scan(&n)
	return n, err
}

// RequeueStale 把「意图已终态或已丢失」但格子仍为 dispatched 的僵尸行退回 pending。
// 仅用于 goalless 收尾前兜底，避免格子永久卡住导致覆盖度不闭合。
func (s *CellStore) RequeueStale(taskID int64) (int64, error) {
	res, err := s.db.Exec(`
UPDATE ca_cells c
SET status = CASE WHEN c.attempts + 1 >= 3 THEN 'failed' ELSE 'pending' END,
    attempts = c.attempts + 1,
    last_error = 'stale: intent 已结束或丢失',
    intent_id = NULL,
    updated_at = now()
WHERE c.task_id=$1 AND c.status='dispatched'
  AND (c.intent_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM exploration_nodes n
        WHERE n.id=c.intent_id AND n.state IN ('open','running')))`, taskID)
	if err != nil {
		return 0, err
	}
	return res.RowsAffected()
}

// Count 返回任务的矩阵格子数（0 = 非矩阵任务）。
func (s *CellStore) Count(taskID int64) (int, error) {
	var n int
	err := s.db.QueryRow(`SELECT count(*) FROM ca_cells WHERE task_id=$1`, taskID).Scan(&n)
	return n, err
}
