from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from followups.domain.models import Category, Prospect, Reply, Track


def test_reply_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone aware"):
        Reply(id="r1", prospect_id="p1", text="hi", received_at=datetime(2026, 10, 15))


def test_reply_accepts_aware_datetime():
    r = Reply(
        id="r1",
        prospect_id="p1",
        text="hi",
        received_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
    )
    assert r.id == "r1"


def test_prospect_is_frozen():
    p = Prospect(id="p1", name="A", company="B", role="C", linkedin_url="u")
    with pytest.raises(FrozenInstanceError):
        p.name = "X"


def test_every_category_is_a_known_string():
    assert {c.value for c in Category} == {
        "INTERESTED",
        "BOOK_CALL",
        "OBJECTION",
        "NOT_INTERESTED",
        "REFERRAL",
        "UNCLEAR",
    }


def test_every_track_is_a_known_string():
    assert {t.value for t in Track} == {"DECK", "VIDEO", "VISUAL", "NONE"}
