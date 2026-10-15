from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from followups.domain.cadence import CadenceConfig, ProspectHistory, evaluate
from followups.domain.models import Track

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
CONFIG = CadenceConfig()


def history(**kw) -> ProspectHistory:
    base = dict(
        tracks_sent=frozenset(),
        last_sent_at=None,
        touches=0,
        last_reply_at=NOW,
        has_open_queue=False,
    )
    base.update(kw)
    return ProspectHistory(**base)


@pytest.mark.parametrize(
    "hist,track,expected_reason",
    [
        (history(tracks_sent=frozenset({Track.DECK})), Track.DECK, "track already sent"),
        (history(last_sent_at=NOW - timedelta(hours=47)), Track.VIDEO, "minimum gap"),
        (
            history(last_sent_at=NOW - timedelta(days=4), last_reply_at=NOW - timedelta(days=4)),
            Track.VIDEO,
            "dormant",
        ),
        (history(touches=3), Track.VIDEO, "max touches"),
        (history(has_open_queue=True), Track.VIDEO, "open follow-up"),
    ],
)
def test_rule_blocks(hist, track, expected_reason):
    decision = evaluate(hist, track, NOW, CONFIG)
    assert decision.allowed is False
    assert expected_reason in decision.reason


def test_clean_history_allows():
    assert evaluate(ProspectHistory.empty(), Track.DECK, NOW, CONFIG).allowed is True


def test_blocking_reasons_are_reported_in_fixed_order():
    hist = history(touches=3, last_sent_at=NOW)
    assert "max touches" in evaluate(hist, Track.VIDEO, NOW, CONFIG).reason


def test_track_none_is_always_blocked():
    assert evaluate(ProspectHistory.empty(), Track.NONE, NOW, CONFIG).allowed is False


def test_a_fresh_reply_resets_dormancy():
    hist = history(last_sent_at=NOW - timedelta(days=4), last_reply_at=NOW - timedelta(hours=1))
    assert evaluate(hist, Track.VIDEO, NOW, CONFIG).allowed is True


def test_gap_exactly_at_the_boundary_is_allowed():
    hist = history(last_sent_at=NOW - timedelta(hours=48))
    assert evaluate(hist, Track.VIDEO, NOW, CONFIG).allowed is True
