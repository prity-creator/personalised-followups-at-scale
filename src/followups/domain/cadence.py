"""Cadence rules.

Pure functions over timestamps. These are the rules that stop the system
embarrassing its operator, so they are the most heavily tested part of the
codebase and deliberately contain no I/O.

Rules are evaluated in a fixed order and the first block wins, because the
reason is shown to a human who wants the most important one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from followups.domain.models import Track


@dataclass(frozen=True)
class CadenceConfig:
    min_gap_hours: int = 48
    silence_days: int = 3
    max_touches: int = 3


@dataclass(frozen=True)
class CadenceDecision:
    allowed: bool
    reason: str = ""


@dataclass(frozen=True)
class ProspectHistory:
    tracks_sent: frozenset[Track]
    last_sent_at: datetime | None
    touches: int
    last_reply_at: datetime | None
    has_open_queue: bool

    @classmethod
    def empty(cls) -> ProspectHistory:
        return cls(
            tracks_sent=frozenset(),
            last_sent_at=None,
            touches=0,
            last_reply_at=None,
            has_open_queue=False,
        )


def _is_dormant(history: ProspectHistory, now: datetime, config: CadenceConfig) -> bool:
    """Dormant means: we sent something, and nothing came back in time.

    A reply that arrived after the last send resets dormancy, which is why the
    comparison is against the reply, not only the clock.
    """
    if history.last_sent_at is None:
        return False
    deadline = history.last_sent_at + timedelta(days=config.silence_days)
    if now < deadline:
        return False
    return history.last_reply_at is None or history.last_reply_at <= history.last_sent_at


def evaluate(
    history: ProspectHistory,
    track: Track,
    now: datetime,
    config: CadenceConfig,
) -> CadenceDecision:
    """Decide whether `track` may be queued for this prospect right now."""
    if track is Track.NONE:
        return CadenceDecision(False, "no track routed for this category")

    if history.touches >= config.max_touches:
        return CadenceDecision(False, f"max touches reached ({config.max_touches})")

    if track in history.tracks_sent:
        return CadenceDecision(False, f"track already sent ({track.value})")

    if history.has_open_queue:
        return CadenceDecision(False, "open follow-up already awaiting approval")

    if _is_dormant(history, now, config):
        return CadenceDecision(False, f"dormant, silent for {config.silence_days} days")

    if history.last_sent_at is not None:
        gap = now - history.last_sent_at
        if gap < timedelta(hours=config.min_gap_hours):
            return CadenceDecision(False, f"minimum gap not met ({config.min_gap_hours}h)")

    return CadenceDecision(True, "")
