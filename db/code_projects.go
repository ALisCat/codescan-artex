package db

import (
	"database/sql"
	"fmt"
	"time"
)

type CodeProject struct {
	ID                 int64      `json:"id"`
	Name               string     `json:"name"`
	Path               string     `json:"path"`
	GitLabProjectID    int64      `json:"gitlab_project_id"`
	WebURL             string     `json:"web_url"`
	DefaultBranch      string     `json:"default_branch"`
	TrackedBranch      string     `json:"tracked_branch"`
	LastSeenCommit     string     `json:"last_seen_commit"`
	LastAuditedCommit  string     `json:"last_audited_commit"`
	LastReviewedCommit string     `json:"last_reviewed_commit"`
	LastReviewedAt     *time.Time `json:"last_reviewed_at,omitempty"`
	LastReviewedBy     *int64     `json:"last_reviewed_by,omitempty"`
	LastReviewNote     string     `json:"last_review_note"`
	LastCheckedAt      *time.Time `json:"last_checked_at,omitempty"`
	LastCheckError     string     `json:"last_check_error"`
	Status             string     `json:"status"`
	CreatedBy          *int64     `json:"created_by,omitempty"`
	CreatedAt          time.Time  `json:"created_at"`
	UpdatedAt          time.Time  `json:"updated_at"`
}

type CodeProjectStore struct{ db *DB }

func (d *DB) CodeProjects() *CodeProjectStore { return &CodeProjectStore{db: d} }

const codeProjectCols = `id,name,path,gitlab_project_id,web_url,default_branch,tracked_branch,
last_seen_commit,last_audited_commit,last_reviewed_commit,last_reviewed_at,last_reviewed_by,last_review_note,
last_checked_at,last_check_error,status,created_by,created_at,updated_at`

func scanCodeProject(sc interface{ Scan(...any) error }) (*CodeProject, error) {
	var p CodeProject
	var checked sql.NullTime
	var createdBy sql.NullInt64
	var reviewedAt sql.NullTime
	var reviewedBy sql.NullInt64
	if err := sc.Scan(&p.ID, &p.Name, &p.Path, &p.GitLabProjectID, &p.WebURL, &p.DefaultBranch, &p.TrackedBranch,
		&p.LastSeenCommit, &p.LastAuditedCommit, &p.LastReviewedCommit, &reviewedAt, &reviewedBy, &p.LastReviewNote,
		&checked, &p.LastCheckError, &p.Status,
		&createdBy, &p.CreatedAt, &p.UpdatedAt); err != nil {
		return nil, err
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
func (s *CodeProjectStore) MarkAuditedAndReviewed(id int64, commit string) error {
	_, err := s.db.Exec(`
UPDATE code_projects SET last_audited_commit=$2,
    last_seen_commit=COALESCE(NULLIF($2,''), last_seen_commit),
    last_reviewed_commit=$2, last_reviewed_at=now(), last_reviewed_by=NULL,
    last_review_note='审计完成', updated_at=now() WHERE id=$1`, id, commit)
	return err
}

func (s *CodeProjectStore) Delete(id int64) error {
	_, err := s.db.Exec(`DELETE FROM code_projects WHERE id=$1`, id)
	return err
}
