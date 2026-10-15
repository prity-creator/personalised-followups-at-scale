"""HeyReach: reads replies from the LinkedIn inbox and sends messages back.

Docs: https://docs.heyreach.io/hey-reach-api
Auth: every request carries an X-API-KEY header.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterator

from followups.adapters.base import RealAdapter
from followups.adapters.http import HttpError
from followups.domain.models import FollowUp, Prospect, Reply, SendResult

BASE_URL = "https://api.heyreach.io/api/public"
PAGE_SIZE = 100

#: HeyReach marks messages the operator sent with this sender value. Anything
#: else came from the other person, which is what we are looking for.
OUTBOUND_SENDER = "ME"


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class _HeyReachBase(RealAdapter):
    ENV_KEY = "HEYREACH_API_KEY"

    def _post(self, path: str, body: dict) -> Any:
        return self.http.request(
            "POST",
            f"{BASE_URL}{path}",
            headers={"X-API-KEY": self.api_key},
            json_body=body,
        ).json()


class HeyReachInbox(_HeyReachBase):
    """POST /inbox/GetConversationsV3, cursor paginated.

    One conversation can hold several inbound messages, and each becomes its own
    `Reply`. Reply ids are derived from the conversation id and the message
    timestamp rather than a counter, so re-fetching the same message produces
    the same id and the store's primary key drops the duplicate.
    """

    def __init__(self, api_key: str, http=None, max_pages: int = 50, **options) -> None:
        super().__init__(api_key, http=http, **options)
        self.max_pages = max_pages

    def _conversations(self, since: datetime | None) -> Iterator[dict]:
        cursor: str | None = None
        for _ in range(self.max_pages):
            body: dict[str, Any] = {
                "limit": PAGE_SIZE,
                "filters": {
                    "linkedInAccountIds": [],
                    "campaignIds": [],
                    "searchString": "",
                    "tags": [],
                    "latestAutoTagNames": [],
                },
            }
            if since is not None:
                body["from"] = _iso_z(since)
            if cursor:
                body["cursor"] = cursor

            payload = self._post("/inbox/GetConversationsV3", body)
            yield from payload.get("items", [])

            cursor = payload.get("nextCursor")
            if not payload.get("hasNextPage") or not cursor:
                return

    def fetch_replies(self, since: datetime | None) -> list[Reply]:
        replies: list[Reply] = []
        for conversation in self._conversations(since):
            try:
                profile = conversation["correspondentProfile"]
                prospect_id = profile["linkedin_id"]
                conversation_id = conversation["id"]
                account_id = conversation.get("linkedInAccountId")
            except (KeyError, TypeError):
                # A conversation we cannot address is not worth failing the run
                # over. Skipping it loses one reply; raising loses all of them.
                continue

            for message in conversation.get("messages", []):
                if message.get("sender") == OUTBOUND_SENDER:
                    continue
                body = message.get("body")
                created = message.get("createdAt")
                if not body or not created:
                    continue
                received_at = _parse_time(created)
                replies.append(
                    Reply(
                        id=f"{conversation_id}#{_iso_z(received_at)}",
                        prospect_id=prospect_id,
                        text=body,
                        received_at=received_at,
                        conversation_id=conversation_id,
                        account_id=account_id,
                    )
                )
        return replies

    def fetch_prospects(self, since: datetime | None) -> list[Prospect]:
        """The same payload already carries the person, so do not refetch them."""
        found: dict[str, Prospect] = {}
        for conversation in self._conversations(since):
            profile = conversation.get("correspondentProfile") or {}
            prospect_id = profile.get("linkedin_id")
            if not prospect_id or prospect_id in found:
                continue
            name = " ".join(
                part for part in (profile.get("firstName"), profile.get("lastName")) if part
            )
            found[prospect_id] = Prospect(
                id=prospect_id,
                name=name or prospect_id,
                company=profile.get("companyName") or "",
                role=profile.get("position") or profile.get("headline") or "",
                linkedin_url=profile.get("profileUrl") or "",
            )
        return list(found.values())


class HeyReachSender(_HeyReachBase):
    """POST /inbox/SendMessage, replying inside the existing conversation.

    Returns a failed `SendResult` rather than raising, because the pipeline
    records a send failure against one follow-up and carries on with the rest.
    """

    def send(self, follow_up: FollowUp, reply: Reply) -> SendResult:
        if not reply.conversation_id or reply.account_id is None:
            return SendResult(
                ok=False,
                detail="reply has no conversation to answer in; it did not come from HeyReach",
            )

        message = follow_up.message_text
        if follow_up.asset and follow_up.asset.url:
            message = f"{message}\n\n{follow_up.asset.url}"

        try:
            self._post(
                "/inbox/SendMessage",
                {
                    "message": message,
                    "subject": follow_up.asset.title if follow_up.asset else "",
                    "conversationId": reply.conversation_id,
                    "linkedInAccountId": reply.account_id,
                },
            )
        except HttpError as exc:
            return SendResult(ok=False, detail=f"heyreach send failed: {exc}")
        return SendResult(ok=True, detail=f"sent in conversation {reply.conversation_id}")
