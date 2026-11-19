package db

import (
	"database/sql"
	"time"
)

type ProjectAuditRun struct {
	ID           int64      `json:"id"`
	ProjectID    int64      `json:"project_id"`
	Mode         string     `json:"mode"`
	BaseCommit   string     `json:"base_commit"`
	TargetCommit string     `json:"target_commit"`
	BaseTaskID   *int64     `json:"base_task_id,omitempty"`
	TaskID       *int64     `json:"task_id,omitempty"`
	SourcePath   string     `json:"source_path,omitempty"`
	ChangedFiles int        `json:"changed_files"`
	DeltaCells   int        `json:"delta_cells"`
	PreparedAt   *time.Time `json:"prepared_at,omitempty"`
	Status       string     `json:"status"`
	ErrorMessage string     `json:"error_message"`
	CreatedBy    *int64     `json:"created_by,omitempty"`
	CreatedAt    time.Time  `json:"created_at"`
	UpdatedAt    time.Time  `json:"updated_at"`
}

const projectAuditCols = `id,project_id,mode,base_commit,target_commit,base_task_id,task_id,source_path,changed_files,delta_cells,prepared_at,status,error_message,created_by,created_at,updated_at`

func scanProjectAudit(sc interface{ Scan(...any) error }) (*ProjectAuditRun, error) {
	var r ProjectAuditRun
	var baseTaskID sql.NullInt64
	var taskID sql.NullInt64
	var preparedAt sql.NullTime
	var createdBy sql.NullInt64
	if err := sc.Scan(&r.ID, &r.ProjectID, &r.Mode, &r.BaseCommit, &r.TargetCommit, &baseTaskID, &taskID,
		&r.SourcePath, &r.ChangedFiles, &r.DeltaCells, &preparedAt,
		&r.Status, &r.ErrorMessage, &createdBy, &r.CreatedAt, &r.UpdatedAt); err != nil {
		return nil, err
	}
	if baseTaskID.Valid {
		r.BaseTaskID = &baseTaskID.Int64
	}
	if taskID.Valid {
		r.TaskID = &taskID.Int64
	}
	if preparedAt.Valid {
		r.PreparedAt = &preparedAt.Time
	}
	if createdBy.Valid {
		r.CreatedBy = &createdBy.Int64
	}
	return &r, nil
}

func (s *CodeProjectStore) StartAudit(projectID int64, mode, baseCommit, targetCommit string, createdBy *int64) (*ProjectAuditRun, error) {
	var id int64
	err := s.db.QueryRow(`
INSERT INTO project_audit_runs(project_id,mode,base_commit,target_commit,status,created_by)
VALUES ($1,$2,$3,$4,'fetching',$5) RETURNING id`,
		projectID, mode, baseCommit, targetCommit, createdBy).Scan(&id)
	if err != nil {
		return nil, err
	}
	return s.GetAudit(id)
}

func (s *CodeProjectStore) StartIncrementalAudit(projectID, baseTaskID int64, baseCommit, targetCommit string, createdBy *int64) (*ProjectAuditRun, error) {
	var id int64
	err := s.db.QueryRow(`
INSERT INTO project_audit_runs(project_id,mode,base_commit,target_commit,base_task_id,status,created_by)
VALUES ($1,'incremental',$2,$3,$4,'preparing',$5) RETURNING id`,
		projectID, baseCommit, targetCommit, baseTaskID, createdBy).Scan(&id)
	if err != nil {
		return nil, err
	}
	return s.GetAudit(id)
}

func (s *CodeProjectStore) MarkAuditPrepared(id int64, sourcePath string, changedFiles, deltaCells int) error {
	_, err := s.db.Exec(`
UPDATE project_audit_runs SET source_path=$2, changed_files=$3, delta_cells=$4,
    status='prepared', prepared_at=now(), updated_at=now() WHERE id=$1`,
		id, sourcePath, changedFiles, deltaCells)
	return err
}

func (s *CodeProjectStore) GetAudit(id int64) (*ProjectAuditRun, error) {
	r, err := scanProjectAudit(s.db.QueryRow(`SELECT `+projectAuditCols+` FROM project_audit_runs WHERE id=$1`, id))
	if err == sql.ErrNoRows {
		return nil, nil
	}
	return r, err
}

func (s *CodeProjectStore) ListAudits(projectID int64, limit int) ([]ProjectAuditRun, error) {
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	rows, err := s.db.Query(`SELECT `+projectAuditCols+` FROM project_audit_runs WHERE project_id=$1 ORDER BY id DESC LIMIT $2`, projectID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []ProjectAuditRun
	for rows.Next() {
		r, err := scanProjectAudit(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *r)
	}
	return out, rows.Err()
}

// ListPendingAuditRuns returns runs whose task has been created but whose audit
// has not yet reached a terminal audit state. The reconciler uses this to move
// last_audited_commit only after the task really finished.
func (s *CodeProjectStore) ListPendingAuditRuns(limit int) ([]ProjectAuditRun, error) {
	if limit <= 0 || limit > 500 {
		limit = 100
	}
	rows, err := s.db.Query(`SELECT `+projectAuditCols+` FROM project_audit_runs
WHERE task_id IS NOT NULL AND status IN ('ready','running')
ORDER BY id ASC LIMIT $1`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []ProjectAuditRun
	for rows.Next() {
		r, err := scanProjectAudit(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *r)
	}
	return out, rows.Err()
}

func (s *CodeProjectStore) FinishAudit(id int64, taskID *int64, status, errText string) error {
	_, err := s.db.Exec(`
UPDATE project_audit_runs SET task_id=$2, status=$3, error_message=$4, updated_at=now()
WHERE id=$1`, id, taskID, status, errText)
	return err
}
