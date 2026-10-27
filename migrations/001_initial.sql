-- Initial Postgres schema for the v1 pipeline.
-- Mirrors app/adapters/sql_repository.py. Safe to re-run: every statement is guarded.

CREATE TABLE IF NOT EXISTS jobs (
    job_id                  VARCHAR(64) PRIMARY KEY,
    workspace_id            VARCHAR(64) NOT NULL,
    creator_id              VARCHAR(64) NOT NULL,
    status                  VARCHAR(32) NOT NULL,
    stage                   VARCHAR(32),
    source_kind             VARCHAR(16),
    source_location         TEXT,
    source_language_code    VARCHAR(16),
    source_language_origin  VARCHAR(16),
    declared_source_language VARCHAR(16),
    target_languages        JSON NOT NULL,
    lip_sync                BOOLEAN NOT NULL DEFAULT FALSE,
    model_overrides         JSON NOT NULL,
    job_budget_micro_usd    BIGINT NOT NULL,
    parent_job_id           VARCHAR(64),
    derived_mode            VARCHAR(16),
    expires_at              TIMESTAMPTZ,
    error_code              VARCHAR(64),
    error_message           TEXT,
    retryable               BOOLEAN NOT NULL DEFAULT FALSE,
    cancel_requested        BOOLEAN NOT NULL DEFAULT FALSE,
    bundle_frozen           BOOLEAN NOT NULL DEFAULT FALSE,
    review_token_id         VARCHAR(128),
    payload                 JSON NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL,
    updated_at              TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_jobs_workspace_id ON jobs (workspace_id);
CREATE INDEX IF NOT EXISTS ix_jobs_workspace_status_created
    ON jobs (workspace_id, status, created_at);

CREATE TABLE IF NOT EXISTS clips (
    clip_id                 VARCHAR(160) PRIMARY KEY,
    job_id                  VARCHAR(64) NOT NULL,
    ordinal                 INTEGER NOT NULL,
    start_seconds           DOUBLE PRECISION NOT NULL,
    end_seconds             DOUBLE PRECISION NOT NULL,
    spoken_source_text      TEXT NOT NULL,
    hook_title              TEXT NOT NULL,
    caption                 TEXT NOT NULL,
    rationale               TEXT NOT NULL,
    selection_score         DOUBLE PRECISION NOT NULL,
    score_breakdown         JSON NOT NULL,
    base_clip_asset_key     TEXT,
    base_clip_master_key    TEXT,
    created_at              TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_clips_job_id ON clips (job_id);

CREATE TABLE IF NOT EXISTS clip_localizations (
    clip_id                 VARCHAR(160) NOT NULL,
    language                VARCHAR(16) NOT NULL,
    job_id                  VARCHAR(64) NOT NULL,
    localized_hook_title    TEXT NOT NULL,
    localized_caption       TEXT NOT NULL,
    audio_key               TEXT,
    video_key               TEXT,
    lip_sync                BOOLEAN NOT NULL DEFAULT FALSE,
    status                  VARCHAR(16) NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (clip_id, language)
);
CREATE INDEX IF NOT EXISTS ix_clip_localizations_job_id ON clip_localizations (job_id);

CREATE TABLE IF NOT EXISTS cost_ledger (
    entry_id                VARCHAR(64) PRIMARY KEY,
    job_id                  VARCHAR(64) NOT NULL,
    workspace_id            VARCHAR(64) NOT NULL,
    stage                   VARCHAR(32) NOT NULL,
    provider                VARCHAR(64) NOT NULL,
    model                   VARCHAR(160) NOT NULL,
    units                   DOUBLE PRECISION NOT NULL,
    unit_type               VARCHAR(32) NOT NULL,
    base_rate_micro_usd     BIGINT NOT NULL,
    margin                  DOUBLE PRECISION NOT NULL,
    estimated_micro_usd     BIGINT NOT NULL,
    actual_micro_usd        BIGINT,
    rate_card_version       VARCHAR(32) NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_cost_ledger_job_id ON cost_ledger (job_id);
CREATE INDEX IF NOT EXISTS ix_cost_ledger_workspace_id ON cost_ledger (workspace_id);
CREATE INDEX IF NOT EXISTS ix_cost_job_created ON cost_ledger (job_id, created_at);

CREATE TABLE IF NOT EXISTS job_events (
    event_id                VARCHAR(64) PRIMARY KEY,
    job_id                  VARCHAR(64) NOT NULL,
    workspace_id            VARCHAR(64) NOT NULL,
    type                    VARCHAR(64) NOT NULL,
    stage                   VARCHAR(32),
    payload                 JSON NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_job_events_job_id ON job_events (job_id);
CREATE INDEX IF NOT EXISTS ix_job_events_workspace_id ON job_events (workspace_id);
CREATE INDEX IF NOT EXISTS ix_events_job_created ON job_events (job_id, created_at);

CREATE TABLE IF NOT EXISTS notification_outbox (
    event_id                VARCHAR(64) PRIMARY KEY,
    job_id                  VARCHAR(64) NOT NULL,
    workspace_id            VARCHAR(64) NOT NULL,
    type                    VARCHAR(32) NOT NULL,
    payload                 JSON NOT NULL,
    status                  VARCHAR(16) NOT NULL,
    attempts                INTEGER NOT NULL DEFAULT 0,
    last_error              TEXT,
    created_at              TIMESTAMPTZ NOT NULL,
    sent_at                 TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_notification_outbox_job_id ON notification_outbox (job_id);
CREATE INDEX IF NOT EXISTS ix_notification_outbox_workspace_id
    ON notification_outbox (workspace_id);
CREATE INDEX IF NOT EXISTS ix_outbox_status_created
    ON notification_outbox (status, created_at);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    workspace_id            VARCHAR(64) NOT NULL,
    key                     VARCHAR(256) NOT NULL,
    method                  VARCHAR(8) NOT NULL,
    path                    TEXT NOT NULL,
    request_hash            VARCHAR(64) NOT NULL,
    response_status         INTEGER NOT NULL,
    response_body           JSON NOT NULL,
    response_headers        JSON NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL,
    expires_at              TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (workspace_id, key)
);
CREATE INDEX IF NOT EXISTS ix_idempotency_keys_expires_at ON idempotency_keys (expires_at);

CREATE TABLE IF NOT EXISTS review_tokens (
    token_id                VARCHAR(128) PRIMARY KEY,
    job_id                  VARCHAR(64) NOT NULL,
    workspace_id            VARCHAR(64) NOT NULL,
    token_hash              VARCHAR(128) NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL,
    rotated_at              TIMESTAMPTZ,
    revoked_at              TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_review_tokens_job_id ON review_tokens (job_id);
CREATE INDEX IF NOT EXISTS ix_review_tokens_workspace_id ON review_tokens (workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_review_tokens_token_hash ON review_tokens (token_hash);

CREATE TABLE IF NOT EXISTS workspace_settings (
    workspace_id            VARCHAR(64) PRIMARY KEY,
    payload                 JSON NOT NULL,
    updated_at              TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS voice_profiles (
    workspace_id            VARCHAR(64) PRIMARY KEY,
    provider                VARCHAR(32) NOT NULL,
    voice_id                VARCHAR(256) NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL,
    updated_at              TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_audit (
    audit_id                VARCHAR(64) PRIMARY KEY,
    workspace_id            VARCHAR(64) NOT NULL,
    actor                   VARCHAR(64) NOT NULL,
    action                  VARCHAR(64) NOT NULL,
    payload                 JSON NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_workspace_audit_workspace_id ON workspace_audit (workspace_id);

CREATE TABLE IF NOT EXISTS purges (
    purge_id                VARCHAR(64) PRIMARY KEY,
    workspace_id            VARCHAR(64) NOT NULL,
    payload                 JSON NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_purges_workspace_id ON purges (workspace_id);

CREATE TABLE IF NOT EXISTS concurrency_leases (
    workspace_id            VARCHAR(64) NOT NULL,
    job_id                  VARCHAR(64) NOT NULL,
    expires_at              TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (workspace_id, job_id)
);
CREATE INDEX IF NOT EXISTS ix_concurrency_leases_expires_at
    ON concurrency_leases (expires_at);
