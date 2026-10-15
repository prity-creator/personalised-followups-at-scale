from __future__ import annotations

import sqlite3

import pytest

from followups.store.repository import Repository
from followups.store.schema import migrate
from tests.conftest import NOW, make_reply

# The schema as it shipped before conversation routing and asset previews
# existed. Anyone who ran an earlier version has a database shaped like this.
OLD_SCHEMA = """
CREATE TABLE prospects (id TEXT PRIMARY KEY, name TEXT, company TEXT, role TEXT,
  linkedin_url TEXT, created_at TEXT);
CREATE TABLE replies (id TEXT PRIMARY KEY, prospect_id TEXT, text TEXT,
  received_at TEXT, ingested_at TEXT);
CREATE TABLE classifications (reply_id TEXT PRIMARY KEY, category TEXT,
  confidence REAL, signals_json TEXT);
CREATE TABLE follow_ups (id TEXT PRIMARY KEY, prospect_id TEXT, reply_id TEXT,
  track TEXT, asset_url TEXT, asset_title TEXT, message_text TEXT, state TEXT,
  reason TEXT, created_at TEXT, decided_at TEXT, sent_at TEXT);
CREATE TABLE runs (id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT,
  counts_json TEXT);
"""


@pytest.fixture()
def old_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(OLD_SCHEMA)
    conn.commit()
    return conn


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_migrating_an_old_database_adds_the_reply_routing_columns(old_db):
    migrate(old_db)
    assert "conversation_id" in columns(old_db, "replies")
    assert "account_id" in columns(old_db, "replies")


def test_migrating_an_old_database_adds_the_asset_preview_column(old_db):
    migrate(old_db)
    assert "asset_preview" in columns(old_db, "follow_ups")


def test_migrate_is_idempotent(old_db):
    migrate(old_db)
    migrate(old_db)  # must not raise "duplicate column name"
    assert "conversation_id" in columns(old_db, "replies")


def test_an_upgraded_database_can_store_a_reply_with_routing_details(old_db):
    migrate(old_db)
    repo = Repository(old_db)
    repo.upsert_reply(
        make_reply("m1"), NOW
    )
    assert repo.get_reply("m1") is not None
