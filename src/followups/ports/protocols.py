"""The seams between the core and the outside world.

Every external service the system touches is reached through one of these.
Each has a real implementation and a deterministic mock, and both must satisfy
the same contract tests.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from followups.domain.models import (
    Asset,
    AssetBrief,
    Classification,
    FollowUp,
    FollowUpRecord,
    Prospect,
    Reply,
    SendResult,
    Track,
)


@runtime_checkable
class InboxSource(Protocol):
    def fetch_replies(self, since: datetime | None) -> list[Reply]: ...


@runtime_checkable
class Classifier(Protocol):
    def classify(self, reply: Reply, prospect: Prospect) -> Classification: ...


@runtime_checkable
class AssetGenerator(Protocol):
    track: Track

    def generate(self, brief: AssetBrief) -> Asset: ...


@runtime_checkable
class Sender(Protocol):
    def send(self, follow_up: FollowUp) -> SendResult: ...


@runtime_checkable
class CrmSink(Protocol):
    def sync(self, records: list[FollowUpRecord]) -> None: ...
