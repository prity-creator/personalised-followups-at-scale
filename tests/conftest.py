from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from followups.domain.models import (
    Asset,
    Classification,
    Category,
    FollowUp,
    FollowUpState,
    Prospect,
    Reply,
    Track,
)
from followups.store.repository import Repository
from followups.store.schema import migrate

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    yield c
    c.close()


@pytest.fixture()
def repo(conn):
    return Repository(conn)


def make_prospect(pid: str = "p1") -> Prospect:
    return Prospect(
        id=pid, name="Ada Lovelace", company="Analytical Co", role="CTO", linkedin_url="u"
    )


def make_reply(rid: str = "m1", prospect_id: str = "p1", text: str = "sounds good") -> Reply:
    return Reply(id=rid, prospect_id=prospect_id, text=text, received_at=NOW)


def make_asset(track: Track = Track.DECK) -> Asset:
    return Asset(track=track, url="https://example.invalid/a", title="T", preview_path="p.html")


def make_follow_up(
    fid: str = "f1",
    prospect_id: str = "p1",
    reply_id: str = "m1",
    track: Track = Track.DECK,
    state: FollowUpState = FollowUpState.PENDING,
) -> FollowUp:
    return FollowUp(
        id=fid,
        prospect_id=prospect_id,
        reply_id=reply_id,
        track=track,
        asset=make_asset(track),
        message_text="hello",
        state=state,
    )


def make_classification(category: Category = Category.INTERESTED) -> Classification:
    return Classification(category=category, confidence=0.9, signals=("keyword",))
