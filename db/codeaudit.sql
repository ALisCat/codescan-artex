-- 二开：接口 × 漏洞类型 审计矩阵
-- 说明：矩阵只做"派方向"，不做"判正误"。worker 的结论通过 status/verdict 回流。

CREATE TABLE IF NOT EXISTS ca_cells (
    id           BIGSERIAL PRIMARY KEY,
    task_id      BIGINT NOT NULL,
    cell_key     TEXT   NOT NULL,              -- 如 "127:file-upload"
    endpoint_url TEXT   NOT NULL,
    method       TEXT   NOT NULL DEFAULT '',
    vulnclass    TEXT   NOT NULL,
    eligibility  TEXT   NOT NULL DEFAULT 'applicable',  -- applicable | needs_review
    priority     INT    NOT NULL DEFAULT 0,
    bucket       TEXT   NOT NULL DEFAULT '',
    direction    TEXT   NOT NULL,              -- 任务书第一段
    checklist    JSONB  NOT NULL DEFAULT '[]'::jsonb,
    hints        JSONB  NOT NULL DEFAULT '{}'::jsonb,
    hints_note   TEXT   NOT NULL DEFAULT '',
    reason       TEXT   NOT NULL DEFAULT '',
    trace        JSONB  NOT NULL DEFAULT '[]'::jsonb,
    status       TEXT   NOT NULL DEFAULT 'pending',     -- pending|dispatched|confirmed|clean|needs_more|skipped|na|unverified|hold|failed
    verdict      TEXT,
    evidence     JSONB,
    intent_id    BIGINT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (task_id, cell_key)
);

CREATE INDEX IF NOT EXISTS idx_ca_cells_task_status
    ON ca_cells (task_id, status, priority DESC);

CREATE INDEX IF NOT EXISTS idx_ca_cells_intent
    ON ca_cells (intent_id) WHERE intent_id IS NOT NULL;

-- v0.4：重试与失败状态（意图 blocked/exhausted 时格子回填）
ALTER TABLE ca_cells ADD COLUMN IF NOT EXISTS attempts   INT  NOT NULL DEFAULT 0;
ALTER TABLE ca_cells ADD COLUMN IF NOT EXISTS last_error TEXT NOT NULL DEFAULT '';
