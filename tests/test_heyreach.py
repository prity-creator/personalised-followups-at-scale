from __future__ import annotations

from datetime import datetime, timezone

import pytest

from followups.adapters.base import MissingCredentials
from followups.adapters.heyreach import HeyReachInbox, HeyReachSender
from followups.domain.models import Reply
from tests.conftest import make_follow_up
from tests.fakes import FakeHttpClient, ok

SINCE = datetime(2026, 10, 1, tzinfo=timezone.utc)


def conversation(
    conv_id: str = "2-abc==",
    account_id: int = 42,
    messages: list[dict] | None = None,
    first: str = "Ada",
    last: str = "Lovelace",
) -> dict:
    return {
        "id": conv_id,
        "linkedInAccountId": account_id,
        "lastMessageAt": "2026-10-15T09:00:00Z",
        "correspondentProfile": {
            "linkedin_id": "ada-123",
            "profileUrl": "https://linkedin.com/in/ada",
            "firstName": first,
            "lastName": last,
            "companyName": "Analytical Co",
            "position": "CTO",
        },
        "messages": messages
        if messages is not None
        else [
            {"createdAt": "2026-10-15T08:00:00Z", "body": "my opener", "sender": "ME"},
            {"createdAt": "2026-10-15T09:00:00Z", "body": "sounds good", "sender": "CORRESPONDENT"},
        ],
    }


def page(items, cursor=None, more=False) -> dict:
    return {"items": items, "totalCount": len(items), "nextCursor": cursor, "hasNextPage": more}


# -- inbox -----------------------------------------------------------------


def test_fetch_replies_posts_to_get_conversations_v3():
    http = FakeHttpClient(responses=[ok(page([conversation()]))])
    HeyReachInbox("key", http=http).fetch_replies(SINCE)
    call = http.calls[0]
    assert call.method == "POST"
    assert call.url == "https://api.heyreach.io/api/public/inbox/GetConversationsV3"
    assert call.headers["X-API-KEY"] == "key"


def test_fetch_replies_sends_the_since_bound_and_a_full_page():
    http = FakeHttpClient(responses=[ok(page([]))])
    HeyReachInbox("key", http=http).fetch_replies(SINCE)
    body = http.calls[0].json_body
    assert body["limit"] == 100
    assert body["from"] == "2026-10-01T00:00:00Z"
    assert "filters" in body


def test_fetch_replies_omits_from_when_there_is_no_watermark():
    http = FakeHttpClient(responses=[ok(page([]))])
    HeyReachInbox("key", http=http).fetch_replies(None)
    assert "from" not in http.calls[0].json_body


def test_only_inbound_messages_become_replies():
    http = FakeHttpClient(responses=[ok(page([conversation()]))])
    replies = HeyReachInbox("key", http=http).fetch_replies(SINCE)
    assert [r.text for r in replies] == ["sounds good"]


def test_a_reply_carries_what_the_sender_will_need():
    http = FakeHttpClient(responses=[ok(page([conversation()]))])
    reply = HeyReachInbox("key", http=http).fetch_replies(SINCE)[0]
    assert reply.prospect_id == "ada-123"
    assert reply.conversation_id == "2-abc=="
    assert reply.account_id == 42
    assert reply.received_at == datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)


def test_reply_ids_are_stable_across_two_fetches():
    first = HeyReachInbox("k", http=FakeHttpClient(responses=[ok(page([conversation()]))]))
    second = HeyReachInbox("k", http=FakeHttpClient(responses=[ok(page([conversation()]))]))
    assert first.fetch_replies(SINCE)[0].id == second.fetch_replies(SINCE)[0].id


def test_fetch_replies_follows_the_cursor_until_the_last_page():
    http = FakeHttpClient(
        responses=[
            ok(page([conversation("c1")], cursor="CUR1", more=True)),
            ok(page([conversation("c2")], cursor=None, more=False)),
        ]
    )
    replies = HeyReachInbox("key", http=http).fetch_replies(SINCE)
    assert len(http.calls) == 2
    assert http.calls[1].json_body["cursor"] == "CUR1"
    assert len(replies) == 2


def test_pagination_stops_at_the_page_cap_rather_than_looping_forever():
    # A server that always says hasNextPage must not hang the run.
    http = FakeHttpClient(
        responses=[ok(page([conversation(f"c{i}")], cursor="SAME", more=True)) for i in range(50)]
    )
    HeyReachInbox("key", http=http, max_pages=5).fetch_replies(SINCE)
    assert len(http.calls) == 5


def test_conversation_with_no_inbound_messages_yields_nothing():
    quiet = conversation(messages=[{"createdAt": "2026-10-15T08:00:00Z", "body": "x", "sender": "ME"}])
    http = FakeHttpClient(responses=[ok(page([quiet]))])
    assert HeyReachInbox("key", http=http).fetch_replies(SINCE) == []


def test_a_malformed_conversation_is_skipped_not_fatal():
    http = FakeHttpClient(responses=[ok(page([{"id": "broken"}, conversation()]))])
    replies = HeyReachInbox("key", http=http).fetch_replies(SINCE)
    assert [r.text for r in replies] == ["sounds good"]


def test_fetch_prospects_builds_people_from_the_same_payload():
    http = FakeHttpClient(responses=[ok(page([conversation()]))])
    prospect = HeyReachInbox("key", http=http).fetch_prospects(SINCE)[0]
    assert prospect.id == "ada-123"
    assert prospect.name == "Ada Lovelace"
    assert prospect.company == "Analytical Co"
    assert prospect.role == "CTO"


def test_inbox_requires_a_key():
    with pytest.raises(MissingCredentials):
        HeyReachInbox("")


# -- sender ----------------------------------------------------------------


def reply_for_send() -> Reply:
    return Reply(
        id="r1",
        prospect_id="ada-123",
        text="sounds good",
        received_at=SINCE,
        conversation_id="2-abc==",
        account_id=42,
    )


def test_send_posts_the_message_with_the_asset_url():
    http = FakeHttpClient(responses=[ok({})])
    result = HeyReachSender("key", http=http).send(make_follow_up("f1"), reply_for_send())
    body = http.calls[0].json_body
    assert http.calls[0].url == "https://api.heyreach.io/api/public/inbox/SendMessage"
    assert body["conversationId"] == "2-abc=="
    assert body["linkedInAccountId"] == 42
    assert "https://example.invalid/a" in body["message"]
    assert result.ok is True


def test_send_refuses_a_reply_with_no_conversation():
    orphan = Reply(id="r1", prospect_id="p", text="t", received_at=SINCE)
    result = HeyReachSender("key", http=FakeHttpClient()).send(make_follow_up("f1"), orphan)
    assert result.ok is False
    assert "conversation" in result.detail


def test_send_reports_a_failure_instead_of_raising():
    from followups.adapters.http import HttpError

    class Boom:
        def request(self, *a, **k):
            raise HttpError(403, "POST", "https://x", b'{"errorMessage":"nope"}')

    result = HeyReachSender("key", http=Boom()).send(make_follow_up("f1"), reply_for_send())
    assert result.ok is False
    assert "403" in result.detail
