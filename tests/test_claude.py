from __future__ import annotations

import pytest

from followups.adapters.claude import ClaudeClassifier
from followups.adapters.http import HttpError
from followups.domain.models import Category
from tests.conftest import make_prospect, make_reply
from tests.fakes import FakeHttpClient, ok


def tool_use(category: str, confidence: float, signals=("said so",)) -> dict:
    return {
        "content": [
            {
                "type": "tool_use",
                "name": "classify_reply",
                "input": {
                    "category": category,
                    "confidence": confidence,
                    "signals": list(signals),
                },
            }
        ]
    }


def test_posts_to_the_messages_endpoint_with_the_version_header():
    http = FakeHttpClient(responses=[ok(tool_use("INTERESTED", 0.9))])
    ClaudeClassifier("key", http=http).classify(make_reply(), make_prospect())
    call = http.calls[0]
    assert call.url == "https://api.anthropic.com/v1/messages"
    assert call.headers["x-api-key"] == "key"
    assert call.headers["anthropic-version"] == "2023-06-01"


def test_forces_the_model_to_answer_through_the_tool():
    http = FakeHttpClient(responses=[ok(tool_use("INTERESTED", 0.9))])
    ClaudeClassifier("key", http=http).classify(make_reply(), make_prospect())
    body = http.calls[0].json_body
    assert body["tool_choice"] == {"type": "tool", "name": "classify_reply"}
    assert body["tools"][0]["input_schema"]["properties"]["category"]["enum"] == [
        c.value for c in Category
    ]


def test_the_prompt_carries_the_reply_and_who_sent_it():
    http = FakeHttpClient(responses=[ok(tool_use("INTERESTED", 0.9))])
    ClaudeClassifier("key", http=http).classify(
        make_reply(text="we already use a vendor"), make_prospect()
    )
    prompt = http.calls[0].json_body["messages"][0]["content"]
    assert "we already use a vendor" in prompt
    assert "Analytical Co" in prompt


def test_returns_the_classification_the_model_chose():
    http = FakeHttpClient(responses=[ok(tool_use("OBJECTION", 0.81, ("too expensive",)))])
    result = ClaudeClassifier("key", http=http).classify(make_reply(), make_prospect())
    assert result.category is Category.OBJECTION
    assert result.confidence == 0.81
    assert result.signals == ("too expensive",)


def test_low_confidence_is_rewritten_to_unclear():
    http = FakeHttpClient(responses=[ok(tool_use("INTERESTED", 0.4))])
    result = ClaudeClassifier("key", http=http, confidence_floor=0.6).classify(
        make_reply(), make_prospect()
    )
    assert result.category is Category.UNCLEAR


def test_a_category_the_model_invented_becomes_unclear():
    http = FakeHttpClient(responses=[ok(tool_use("VERY_KEEN", 0.99))])
    result = ClaudeClassifier("key", http=http).classify(make_reply(), make_prospect())
    assert result.category is Category.UNCLEAR


def test_a_response_with_no_tool_use_becomes_unclear():
    http = FakeHttpClient(responses=[ok({"content": [{"type": "text", "text": "I think..."}]})])
    result = ClaudeClassifier("key", http=http).classify(make_reply(), make_prospect())
    assert result.category is Category.UNCLEAR
    assert result.confidence == 0.0


def test_an_api_failure_becomes_unclear_rather_than_an_exception():
    class Boom:
        def request(self, *a, **k):
            raise HttpError(500, "POST", "https://x", b"down")

    result = ClaudeClassifier("key", http=Boom()).classify(make_reply(), make_prospect())
    assert result.category is Category.UNCLEAR


def test_a_missing_prospect_does_not_crash_the_prompt():
    http = FakeHttpClient(responses=[ok(tool_use("INTERESTED", 0.9))])
    result = ClaudeClassifier("key", http=http).classify(make_reply(), None)
    assert result.category is Category.INTERESTED
