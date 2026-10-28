-- Source Uploads (ADR 0022): files uploaded straight to object storage before a Job exists.
-- Mirrors app/adapters/sql_repository.py. Safe to re-run: every statement is guarded.

CREATE TABLE IF NOT EXISTS source_uploads (
    upload_id               VARCHAR(64) PRIMARY KEY,
    workspace_id            VARCHAR(64) NOT NULL,
    key                     VARCHAR(256) NOT NULL UNIQUE,
    provider_upload_id      VARCHAR(1024) NOT NULL,
    filename                VARCHAR(255) NOT NULL,
    content_type            VARCHAR(128) NOT NULL,
    declared_size_bytes     BIGINT NOT NULL,
    actual_size_bytes       BIGINT,
    status                  VARCHAR(16) NOT NULL,
    job_id                  VARCHAR(64),
    created_at              TIMESTAMPTZ NOT NULL,
    completed_at            TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_source_uploads_workspace_id ON source_uploads (workspace_id);
CREATE INDEX IF NOT EXISTS ix_source_uploads_job_id ON source_uploads (job_id);
