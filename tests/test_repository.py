from __future__ import annotations

from datetime import timedelta

from followups.domain.models import Category, FollowUpState, Track
from tests.conftest import (
    NOW,
    make_classification,
    make_follow_up,
    make_prospect,
    make_reply,
)


def test_reingesting_same_message_id_keeps_one_row(repo):
    repo.upsert_reply(make_reply("m1"))
    repo.upsert_reply(make_reply("m1"))
    assert len(repo.unclassified_replies()) == 1


def test_reply_for_unknown_prospect_is_stored(repo):
    repo.upsert_reply(make_reply("m1", prospect_id="ghost"))
    assert repo.unclassified_replies()[0].prospect_id == "ghost"


def test_prospect_for_unknown_id_is_none(repo):
    assert repo.get_prospect("ghost") is None


def test_classified_replies_are_not_returned_again(repo):
    repo.upsert_reply(make_reply("m1"))
    repo.save_classification("m1", make_classification())
    assert repo.unclassified_replies() == []


def test_history_for_unknown_prospect_is_empty(repo):
    h = repo.history_for("ghost")
    assert h.touches == 0
    assert h.tracks_sent == frozenset()
    assert h.has_open_queue is False


def test_history_counts_only_sent_follow_ups(repo):
    repo.upsert_prospect(make_prospect())
    repo.upsert_reply(make_reply("m1"))
    repo.queue(make_follow_up("f1", track=Track.DECK), NOW)
    repo.queue(make_follow_up("f2", track=Track.VIDEO), NOW)
    repo.set_state("f1", FollowUpState.SENT, sent_at=NOW)
    repo.set_state("f2", FollowUpState.REJECTED)
    h = repo.history_for("p1")
    assert h.touches == 1
    assert h.tracks_sent == frozenset({Track.DECK})


def test_history_reports_open_queue_for_pending(repo):
    repo.queue(make_follow_up("f1"), NOW)
    assert repo.history_for("p1").has_open_queue is True


def test_history_reports_open_queue_for_approved(repo):
    repo.queue(make_follow_up("f1"), NOW)
    repo.set_state("f1", FollowUpState.APPROVED)
    assert repo.history_for("p1").has_open_queue is True


def test_history_last_reply_at_tracks_newest_reply(repo):
    repo.upsert_reply(make_reply("m1"))
    later = make_reply("m2")
    object.__setattr__(later, "received_at", NOW + timedelta(hours=5))
    repo.upsert_reply(later)
    assert repo.history_for("p1").last_reply_at == NOW + timedelta(hours=5)


def test_pending_and_approved_are_separate(repo):
    repo.queue(make_follow_up("f1"), NOW)
    repo.queue(make_follow_up("f2", prospect_id="p2", reply_id="m2"), NOW)
    repo.set_state("f2", FollowUpState.APPROVED)
    assert [f.id for f in repo.pending()] == ["f1"]
    assert [f.id for f in repo.approved()] == ["f2"]


def test_set_state_records_reason(repo):
    repo.queue(make_follow_up("f1"), NOW)
    repo.set_state("f1", FollowUpState.FAILED, reason="boom")
    assert repo.all_records()[0].reason == "boom"


def test_all_records_joins_prospect_and_category(repo):
    repo.upsert_prospect(make_prospect())
    repo.upsert_reply(make_reply("m1"))
    repo.save_classification("m1", make_classification(Category.INTERESTED))
    repo.queue(make_follow_up("f1"), NOW)
    record = repo.all_records()[0]
    assert record.prospect_name == "Ada Lovelace"
    assert record.category is Category.INTERESTED


def test_all_records_carries_the_reply_text_for_presentation(repo):
    repo.upsert_prospect(make_prospect())
    repo.upsert_reply(make_reply("m1", text="tell me more about pricing"))
    repo.queue(make_follow_up("f1"), NOW)
    assert repo.all_records()[0].reply_text == "tell me more about pricing"


def test_all_records_carries_the_role_and_classifier_confidence(repo):
    repo.upsert_prospect(make_prospect())
    repo.upsert_reply(make_reply("m1"))
    repo.save_classification("m1", make_classification())
    repo.queue(make_follow_up("f1"), NOW)
    record = repo.all_records()[0]
    assert record.role == "CTO"
    assert record.confidence == 0.9


def test_all_records_carries_the_drafted_message_and_asset(repo):
    repo.queue(make_follow_up("f1"), NOW)
    record = repo.all_records()[0]
    assert record.message_text == "hello"
    assert record.asset_title == "T"
    assert record.asset_preview_path == "p.html"


def test_asset_preview_path_survives_a_round_trip(repo):
    repo.queue(make_follow_up("f1"), NOW)
    assert repo.pending()[0].asset.preview_path == "p.html"


def test_a_record_for_a_reply_that_is_gone_still_renders(repo):
    repo.queue(make_follow_up("f1"), NOW)
    assert repo.all_records()[0].reply_text == ""
