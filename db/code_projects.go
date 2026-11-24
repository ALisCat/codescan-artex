package db

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

type CodeProject struct {
	ID                 int64           `json:"id"`
	Name               string          `json:"name"`
	Path               string          `json:"path"`
	GitLabProjectID    int64           `json:"gitlab_project_id"`
	WebURL             string          `json:"web_url"`
	DefaultBranch      string          `json:"default_branch"`
	TrackedBranch      string          `json:"tracked_branch"`
	LastSeenCommit     string          `json:"last_seen_commit"`
	LastAuditedCommit  string          `json:"last_audited_commit"`
	LastAuditedTaskID  *int64          `json:"last_audited_task_id,omitempty"`
	LastAuditedRunID   *int64          `json:"last_audited_run_id,omitempty"`
	LastReviewedCommit string          `json:"last_reviewed_commit"`
	LastReviewedAt     *time.Time      `json:"last_reviewed_at,omitempty"`
	LastReviewedBy     *int64          `json:"last_reviewed_by,omitempty"`
	LastReviewNote     string          `json:"last_review_note"`
	LastCheckedAt      *time.Time      `json:"last_checked_at,omitempty"`
	LastCheckError     string          `json:"last_check_error"`
	Status             string          `json:"status"`
	AccessProfile      json.RawMessage `json:"access_profile"`
	CreatedBy          *int64          `json:"created_by,omitempty"`
	CreatedAt          time.Time       `json:"created_at"`
	UpdatedAt          time.Time       `json:"updated_at"`
}

type CodeProjectStore struct{ db *DB }

func (d *DB) CodeProjects() *CodeProjectStore { return &CodeProjectStore{db: d} }

const codeProjectCols = `id,name,path,gitlab_project_id,web_url,default_branch,tracked_branch,
last_seen_commit,last_audited_commit,last_audited_task_id,last_audited_run_id,last_reviewed_commit,last_reviewed_at,last_reviewed_by,last_review_note,
last_checked_at,last_check_error,status,COALESCE(access_profile,'{}'::jsonb),created_by,created_at,updated_at`

func scanCodeProject(sc interface{ Scan(...any) error }) (*CodeProject, error) {
	var p CodeProject
	var checked sql.NullTime
	var createdBy sql.NullInt64
	var reviewedAt sql.NullTime
	var reviewedBy sql.NullInt64
	var auditedTaskID sql.NullInt64
	var auditedRunID sql.NullInt64
	var accessProfile []byte
	if err := sc.Scan(&p.ID, &p.Name, &p.Path, &p.GitLabProjectID, &p.WebURL, &p.DefaultBranch, &p.TrackedBranch,
		&p.LastSeenCommit, &p.LastAuditedCommit, &auditedTaskID, &auditedRunID, &p.LastReviewedCommit, &reviewedAt, &reviewedBy, &p.LastReviewNote,
		&checked, &p.LastCheckError, &p.Status, &accessProfile,
		&createdBy, &p.CreatedAt, &p.UpdatedAt); err != nil {
		return nil, err
	}
	if auditedTaskID.Valid {
		p.LastAuditedTaskID = &auditedTaskID.Int64
	}
	if auditedRunID.Valid {
		p.LastAuditedRunID = &auditedRunID.Int64
	}
	if reviewedAt.Valid {
		p.LastReviewedAt = &reviewedAt.Time
	}
	if reviewedBy.Valid {
		p.LastReviewedBy = &reviewedBy.Int64
	}
	if checked.Valid {
		p.LastCheckedAt = &checked.Time
	}
	if createdBy.Valid {
		p.CreatedBy = &createdBy.Int64
	}
	if len(accessProfile) > 0 {
		p.AccessProfile = json.RawMessage(accessProfile)
	}
	if len(p.AccessProfile) == 0 {
		p.AccessProfile = json.RawMessage(`{}`)
	}
	return &p, nil
}

func (s *CodeProjectStore) List() ([]CodeProject, error) {
	rows, err := s.db.Query(`SELECT ` + codeProjectCols + ` FROM code_projects ORDER BY updated_at DESC, id DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []CodeProject
	for rows.Next() {
		p, err := scanCodeProject(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *p)
	}
	return out, rows.Err()
}

// ListPage returns a filtered, sorted page of projects and the total matching count.
// Status values are UI-facing keys: unaudited, audited, update, error.
func (s *CodeProjectStore) ListPage(q, status, sortBy string, page, size int) ([]CodeProject, int, error) {
	if page <= 0 {
		page = 1
	}
	if size <= 0 || size > 100 {
		size = 20
	}
	where := []string{"TRUE"}
	args := []any{}
	addArg := func(v any) int {
		args = append(args, v)
		return len(args)
	}
	if q = strings.TrimSpace(q); q != "" {
		n := addArg("%" + q + "%")
		where = append(where, fmt.Sprintf("(name ILIKE $%d OR path ILIKE $%d)", n, n))
	}
	switch strings.TrimSpace(status) {
	case "unaudited":
		where = append(where, "last_audited_commit = ''")
	case "audited":
		where = append(where, "last_audited_commit <> '' AND last_seen_commit = last_audited_commit AND last_check_error = ''")
	case "update":
		where = append(where, "last_audited_commit <> '' AND last_seen_commit <> last_audited_commit AND last_check_error = ''")
	case "error":
		where = append(where, "last_check_error <> ''")
	}
	clause := strings.Join(where, " AND ")
	order := "updated_at DESC, id DESC"
	switch strings.TrimSpace(sortBy) {
	case "name":
		order = "name ASC, id ASC"
	case "audited":
		order = "last_audited_commit DESC, updated_at DESC, id DESC"
	case "status":
		order = "CASE WHEN last_check_error <> '' THEN 0 WHEN last_audited_commit = '' THEN 1 WHEN last_seen_commit <> last_audited_commit THEN 2 ELSE 3 END, updated_at DESC, id DESC"
	}
	var total int
	if err := s.db.QueryRow(`SELECT count(*) FROM code_projects WHERE `+clause, args...).Scan(&total); err != nil {
		return nil, 0, err
	}
	offset := (page - 1) * size
	args = append(args, size, offset)
	limitN := len(args) - 1
	rows, err := s.db.Query(`SELECT `+codeProjectCols+` FROM code_projects WHERE `+clause+
		fmt.Sprintf(" ORDER BY %s LIMIT $%d OFFSET $%d", order, limitN, limitN+1), args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	out := []CodeProject{}
	for rows.Next() {
		p, err := scanCodeProject(rows)
		if err != nil {
			return nil, 0, err
		}
		out = append(out, *p)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, err
	}
	return out, total, nil
}

func (s *CodeProjectStore) Get(id int64) (*CodeProject, error) {
	if id <= 0 {
		return nil, nil
	}
	p, err := scanCodeProject(s.db.QueryRow(`SELECT `+codeProjectCols+` FROM code_projects WHERE id=$1`, id))
	if err == sql.ErrNoRows {
		return nil, nil
	}
	return p, err
}

func (s *CodeProjectStore) GetByPath(path string) (*CodeProject, error) {
	p, err := scanCodeProject(s.db.QueryRow(`SELECT `+codeProjectCols+` FROM code_projects WHERE path=$1`, path))
	if err == sql.ErrNoRows {
		return nil, nil
	}
	return p, err
}

func (s *CodeProjectStore) Create(p CodeProject) (*CodeProject, error) {
	if p.Name == "" || p.Path == "" {
		return nil, fmt.Errorf("项目名称和路径不能为空")
	}
	if p.DefaultBranch == "" {
		p.DefaultBranch = "main"
	}
	if p.TrackedBranch == "" {
		p.TrackedBranch = p.DefaultBranch
	}
	if p.Status == "" {
		p.Status = "active"
	}
	var id int64
	err := s.db.QueryRow(`
INSERT INTO code_projects(name,path,gitlab_project_id,web_url,default_branch,tracked_branch,last_seen_commit,status,created_by)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
ON CONFLICT (path,tracked_branch) DO UPDATE SET
    name=EXCLUDED.name,
    gitlab_project_id=EXCLUDED.gitlab_project_id,
    web_url=EXCLUDED.web_url,
    default_branch=EXCLUDED.default_branch,
    last_seen_commit=COALESCE(NULLIF(EXCLUDED.last_seen_commit,''), code_projects.last_seen_commit),
    updated_at=now()
RETURNING id`,
		p.Name, p.Path, p.GitLabProjectID, p.WebURL, p.DefaultBranch, p.TrackedBranch, p.LastSeenCommit, p.Status, p.CreatedBy).Scan(&id)
	if err != nil {
		return nil, err
	}
	return s.Get(id)
}

func (s *CodeProjectStore) UpdateCheck(id int64, head, errText string) error {
	_, err := s.db.Exec(`
UPDATE code_projects SET
    last_seen_commit = COALESCE(NULLIF($2,''), last_seen_commit),
    last_checked_at = now(),
    last_check_error = $3,
    updated_at = now()
WHERE id=$1`, id, head, errText)
	return err
}

func (s *CodeProjectStore) MarkAudited(id int64, commit string) error {
	_, err := s.db.Exec(`
UPDATE code_projects SET last_audited_commit=$2, last_seen_commit=COALESCE(NULLIF($2,''), last_seen_commit),
    updated_at=now() WHERE id=$1`, id, commit)
	return err
}

// MarkReviewed records a human triage decision ("reviewed, no audit") without
// moving the audit baseline. The audit gap remains visible until a real audit
// completes.
func (s *CodeProjectStore) MarkReviewed(id int64, commit string, by *int64, note string) error {
	_, err := s.db.Exec(`
UPDATE code_projects SET last_reviewed_commit=$2, last_reviewed_at=now(), last_reviewed_by=$3,
    last_review_note=$4, updated_at=now() WHERE id=$1`, id, commit, by, note)
	return err
}

// MarkAuditedAndReviewed is called after an audit task reaches done: the target
// commit is both audited and reviewed.
func (s *CodeProjectStore) MarkAuditedAndReviewed(id int64, commit string, taskID, runID int64) error {
	_, err := s.db.Exec(`
UPDATE code_projects SET last_audited_commit=$2,
    last_audited_task_id=$3, last_audited_run_id=$4,
    last_seen_commit=COALESCE(NULLIF($2,''), last_seen_commit),
    last_reviewed_commit=$2, last_reviewed_at=now(), last_reviewed_by=NULL,
    last_review_note='审计完成', updated_at=now() WHERE id=$1`, id, commit, taskID, runID)
	return err
}

func (s *CodeProjectStore) SetAccessProfile(id int64, raw json.RawMessage) error {
	if len(raw) == 0 {
		raw = json.RawMessage(`{}`)
	}
	_, err := s.db.Exec(`UPDATE code_projects SET access_profile=$2::jsonb, updated_at=now() WHERE id=$1`, id, string(raw))
	return err
}

func (s *CodeProjectStore) Delete(id int64) error {
	_, err := s.db.Exec(`DELETE FROM code_projects WHERE id=$1`, id)
	return err
}
