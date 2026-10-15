"""SQLite schema and migration.

Idempotency is a property of the schema, not of the pipeline: replies.id is the
provider's own message id and the primary key, so re-ingesting a reply the
system has already seen is a no-op at the database level.
"""

from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS prospects (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    company       TEXT NOT NULL,
    role          TEXT NOT NULL,
    linkedin_url  TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS replies (
    id           TEXT PRIMARY KEY,
    prospect_id  TEXT NOT NULL,
    text         TEXT NOT NULL,
    received_at  TEXT NOT NULL,
    ingested_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS classifications (
    reply_id     TEXT PRIMARY KEY,
    category     TEXT NOT NULL,
    confidence   REAL NOT NULL,
    signals_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS follow_ups (
    id           TEXT PRIMARY KEY,
    prospect_id  TEXT NOT NULL,
    reply_id     TEXT NOT NULL,
    track        TEXT NOT NULL,
    asset_url    TEXT NOT NULL DEFAULT '',
    asset_title  TEXT NOT NULL DEFAULT '',
    message_text TEXT NOT NULL DEFAULT '',
    state        TEXT NOT NULL,
    reason       TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    decided_at   TEXT,
    sent_at      TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    counts_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_replies_prospect ON replies(prospect_id);
CREATE INDEX IF NOT EXISTS idx_follow_ups_prospect ON follow_ups(prospect_id);
CREATE INDEX IF NOT EXISTS idx_follow_ups_state ON follow_ups(state);
"""


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
