from __future__ import annotations

import json
from pathlib import Path

import pytest

from followups.adapters.mock import (
    FileSender,
    FixtureInbox,
    HtmlDashboardSink,
    KeywordClassifier,
)
from followups.adapters.registry import default_registry
from followups.domain.models import Category, FollowUpState
from tests.conftest import NOW, make_follow_up, make_prospect, make_reply

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_default_registry_is_all_mocks(tmp_path):
    for adapter in default_registry(tmp_path).all_adapters():
        assert type(adapter).__module__ == "followups.adapters.mock", adapter


@pytest.mark.parametrize(
    "text,expected",
    [
        ("This sounds good, tell me more", Category.INTERESTED),
        ("can we book a call on Tuesday?", Category.BOOK_CALL),
        ("this looks too expensive for us", Category.OBJECTION),
        ("Not interested, please remove me", Category.NOT_INTERESTED),
        ("you should reach out to our Head of Growth", Category.REFERRAL),
    ],
)
def test_keyword_classifier_recognises_each_category(text, expected):
    result = KeywordClassifier().classify(make_reply(text=text), make_prospect())
    assert result.category is expected


def test_not_interested_wins_over_interested():
    result = KeywordClassifier().classify(
        make_reply(text="I am not interested"), make_prospect()
    )
    assert result.category is Category.NOT_INTERESTED


def test_low_confidence_is_rewritten_to_unclear():
    result = KeywordClassifier(confidence_floor=0.6).classify(
        make_reply(text="Hmm."), make_prospect()
    )
    assert result.category is Category.UNCLEAR
    assert result.confidence < 0.6


def test_classifier_is_deterministic():
    reply, prospect = make_reply(), make_prospect()
    assert KeywordClassifier().classify(reply, prospect) == KeywordClassifier().classify(
        reply, prospect
    )


def test_fixture_inbox_reads_every_reply():
    replies = FixtureInbox(FIXTURES / "replies.json").fetch_replies(since=None)
    assert len(replies) == 6
    assert all(r.received_at.tzinfo is not None for r in replies)


def test_fixture_inbox_filters_by_since():
    import datetime as dt

    cutoff = dt.datetime(2026, 10, 15, 9, 25, tzinfo=dt.timezone.utc)
    assert len(FixtureInbox(FIXTURES / "replies.json").fetch_replies(since=cutoff)) == 3


def test_file_sender_appends_one_line_per_send(tmp_path):
    out = tmp_path / "outbox.jsonl"
    sender = FileSender(out)
    assert sender.send(make_follow_up("f1")).ok is True
    sender.send(make_follow_up("f2"))
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["follow_up_id"] == "f1"


def test_html_dashboard_sink_writes_a_table(tmp_path, repo):
    repo.queue(make_follow_up("f1"), NOW)
    out = tmp_path / "dashboard.html"
    HtmlDashboardSink(out).sync(repo.all_records())
    assert "<table" in out.read_text()


def test_html_dashboard_escapes_untrusted_text(tmp_path, repo):
    repo.upsert_prospect(make_prospect())
    repo.queue(make_follow_up("f1"), NOW)
    repo.set_state("f1", FollowUpState.FAILED, reason="<script>alert(1)</script>")
    out = tmp_path / "dashboard.html"
    HtmlDashboardSink(out).sync(repo.all_records())
    assert "<script>alert(1)</script>" not in out.read_text()
