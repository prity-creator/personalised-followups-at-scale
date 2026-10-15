"""Domain models.

Frozen dataclasses and enums only. This module performs no I/O and imports
nothing from the adapter, store, pipeline or cli layers. The architecture test
enforces that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Category(str, Enum):
    """What an inbound reply is saying."""

    INTERESTED = "INTERESTED"
    BOOK_CALL = "BOOK_CALL"
    OBJECTION = "OBJECTION"
    NOT_INTERESTED = "NOT_INTERESTED"
    REFERRAL = "REFERRAL"
    UNCLEAR = "UNCLEAR"


class Track(str, Enum):
    """Which kind of personalised resource to produce."""

    DECK = "DECK"
    VIDEO = "VIDEO"
    VISUAL = "VISUAL"
    NONE = "NONE"


class FollowUpState(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone aware")


@dataclass(frozen=True)
class Prospect:
    id: str
    name: str
    company: str
    role: str
    linkedin_url: str


@dataclass(frozen=True)
class Reply:
    id: str
    prospect_id: str
    text: str
    received_at: datetime
    # Provider routing details, needed to reply in the same thread. Empty for
    # fixture data, populated by a real inbox adapter.
    conversation_id: str = ""
    account_id: int | None = None

    def __post_init__(self) -> None:
        _require_aware(self.received_at, "received_at")


@dataclass(frozen=True)
class Classification:
    category: Category
    confidence: float
    signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class Asset:
    track: Track
    url: str
    title: str
    preview_path: str


@dataclass(frozen=True)
class AssetBrief:
    prospect: Prospect
    reply: Reply
    classification: Classification


@dataclass(frozen=True)
class FollowUp:
    id: str
    prospect_id: str
    reply_id: str
    track: Track
    asset: Asset | None
    message_text: str
    state: FollowUpState = FollowUpState.PENDING
    reason: str = ""


@dataclass(frozen=True)
class SendResult:
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class FollowUpRecord:
    """One flattened row for presentation surfaces.

    Everything a dashboard, a sheet or a CRM needs to show a follow-up without
    querying anything else, including the reply it answers. The fields after
    created_at carry defaults so a sink written against an earlier shape keeps
    working.
    """

    follow_up_id: str
    prospect_name: str
    company: str
    category: Category
    track: Track
    state: FollowUpState
    reason: str
    asset_url: str
    created_at: datetime
    role: str = ""
    reply_text: str = ""
    message_text: str = ""
    asset_title: str = ""
    asset_preview_path: str = ""
    confidence: float = 0.0
