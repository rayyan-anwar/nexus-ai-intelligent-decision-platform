-- NEXUS AI reference schema (SQLite dialect).
--
-- Source of truth for deployments is the Alembic migration in database/migrations/versions/,
-- which targets both SQLite and PostgreSQL. This file is a readable snapshot used for
-- documentation and for testing the analytical queries in queries.sql
-- (backend/tests/test_sql_schema.py runs it against an in-memory SQLite database).
--
-- No raw dataset rows are stored here: datasets live as files under the data directory and are
-- removed on expiry/deletion; the database keeps metadata only.

PRAGMA foreign_keys = ON;

CREATE TABLE datasets (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    stored_filename  TEXT NOT NULL UNIQUE,          -- generated; never derived from the upload name
    sha256           TEXT NOT NULL,
    n_rows           INTEGER NOT NULL CHECK (n_rows >= 0),
    n_cols           INTEGER NOT NULL CHECK (n_cols >= 1),
    size_bytes       INTEGER NOT NULL CHECK (size_bytes >= 0),
    is_synthetic     INTEGER NOT NULL DEFAULT 0 CHECK (is_synthetic IN (0, 1)),
    profile_json     TEXT NOT NULL,
    created_at       TIMESTAMP NOT NULL,
    expires_at       TIMESTAMP                      -- retention deadline; NULL = keep until deleted
);
CREATE INDEX ix_datasets_sha256     ON datasets (sha256);
CREATE INDEX ix_datasets_expires_at ON datasets (expires_at);

CREATE TABLE experiments (
    id                   TEXT PRIMARY KEY,
    dataset_id           TEXT NOT NULL REFERENCES datasets (id) ON DELETE CASCADE,
    target               TEXT NOT NULL,
    task                 TEXT CHECK (task IN ('binary', 'multiclass', 'regression')),
    status               TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    progress             REAL NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 1),
    stage                TEXT,
    seed                 INTEGER NOT NULL,
    dataset_fingerprint  TEXT NOT NULL,
    config_json          TEXT NOT NULL,
    summary_json         TEXT,
    error_message        TEXT,                      -- safe, user-facing text only
    created_at           TIMESTAMP NOT NULL,
    started_at           TIMESTAMP,
    finished_at          TIMESTAMP
);
CREATE INDEX ix_experiments_dataset_id    ON experiments (dataset_id);
CREATE INDEX ix_experiments_status_created ON experiments (status, created_at);

CREATE TABLE models (
    id                TEXT PRIMARY KEY,
    experiment_id     TEXT NOT NULL UNIQUE REFERENCES experiments (id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    task              TEXT NOT NULL CHECK (task IN ('binary', 'multiclass', 'regression')),
    target            TEXT NOT NULL,
    artifact_filename TEXT NOT NULL UNIQUE,
    artifact_sha256   TEXT NOT NULL,
    metadata_json     TEXT NOT NULL,
    created_at        TIMESTAMP NOT NULL
);
CREATE INDEX ix_models_target_created ON models (target, created_at);

CREATE TABLE prediction_events (
    id            TEXT PRIMARY KEY,
    model_id      TEXT NOT NULL REFERENCES models (id) ON DELETE CASCADE,
    n_records     INTEGER NOT NULL CHECK (n_records > 0),
    input_sha256  TEXT NOT NULL,                    -- hash of the request only; inputs are never stored
    summary_json  TEXT NOT NULL,
    created_at    TIMESTAMP NOT NULL
);
CREATE INDEX ix_prediction_events_model_created ON prediction_events (model_id, created_at);

CREATE TABLE audit_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at    TIMESTAMP NOT NULL,
    actor          TEXT NOT NULL,
    action         TEXT NOT NULL,
    resource_type  TEXT NOT NULL,
    resource_id    TEXT,
    detail_json    TEXT
);
CREATE INDEX ix_audit_events_occurred_at ON audit_events (occurred_at);
CREATE INDEX ix_audit_events_resource    ON audit_events (resource_type, resource_id);
