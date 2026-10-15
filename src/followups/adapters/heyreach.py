"""HeyReach: reads replies from the LinkedIn inbox and sends messages back."""

from __future__ import annotations

from datetime import datetime

from followups.adapters.base import RealAdapter
from followups.domain.models import FollowUp, Reply, SendResult

DOCS = "https://documenter.getpostman.com/view/23808049/2sA2xb5F75"


class HeyReachInbox(RealAdapter):
    """GET /inbox/messages, paginated, filtered to inbound messages since a cursor."""

    ENV_KEY = "HEYREACH_API_KEY"

    def fetch_replies(self, since: datetime | None) -> list[Reply]:
        raise self._not_implemented("GET /inbox/messages", DOCS)


class HeyReachSender(RealAdapter):
    """POST /inbox/send, one message per approved follow-up, asset url appended."""

    ENV_KEY = "HEYREACH_API_KEY"

    def send(self, follow_up: FollowUp) -> SendResult:
        raise self._not_implemented("POST /inbox/send", DOCS)
