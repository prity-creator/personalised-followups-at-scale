from __future__ import annotations

import pytest

from followups.adapters.gamma import GammaDeckGenerator
from followups.adapters.http import HttpError
from followups.domain.models import AssetBrief, Track
from tests.conftest import make_classification, make_prospect, make_reply
from tests.fakes import FakeHttpClient, ok


def brief() -> AssetBrief:
    return AssetBrief(make_prospect(), make_reply(), make_classification())


def generator(http, **kw) -> GammaDeckGenerator:
    return GammaDeckGenerator("key", http=http, sleep=lambda _s: None, **kw)


def started(gen_id="g1") -> dict:
    return {"generationId": gen_id}


def status(state, url="https://gamma.app/docs/abc123") -> dict:
    payload = {"generationId": "g1", "status": state}
    if state == "completed":
        payload["gammaUrl"] = url
    return payload


def test_starts_a_generation_at_the_public_api():
    http = FakeHttpClient(responses=[ok(started()), ok(status("completed"))])
    generator(http).generate(brief())
    call = http.calls[0]
    assert call.method == "POST"
    assert call.url == "https://public-api.gamma.app/v1.0/generations"
    assert call.headers["X-API-KEY"] == "key"


def test_the_prompt_is_built_from_the_prospect_and_their_reply():
    http = FakeHttpClient(responses=[ok(started()), ok(status("completed"))])
    generator(http).generate(brief())
    body = http.calls[0].json_body
    assert "Analytical Co" in body["inputText"]
    assert "sounds good" in body["inputText"]
    assert body["format"] == "presentation"
    assert body["textMode"] == "generate"


def test_polls_the_status_endpoint_until_completed():
    http = FakeHttpClient(
        responses=[ok(started()), ok(status("pending")), ok(status("completed"))]
    )
    asset = generator(http).generate(brief())
    assert http.calls[1].url == "https://public-api.gamma.app/v1.0/generations/g1"
    assert http.calls[1].method == "GET"
    assert asset.url == "https://gamma.app/docs/abc123"
    assert asset.track is Track.DECK


def test_gives_up_after_the_poll_budget():
    http = FakeHttpClient(responses=[ok(started())] + [ok(status("pending"))] * 10)
    with pytest.raises(RuntimeError, match="did not finish"):
        generator(http, max_polls=4).generate(brief())


def test_a_failed_generation_raises_with_the_reason():
    failed = {"generationId": "g1", "status": "failed", "error": {"message": "no credits"}}
    http = FakeHttpClient(responses=[ok(started()), ok(failed)])
    with pytest.raises(RuntimeError, match="no credits"):
        generator(http).generate(brief())


def test_a_start_that_returns_no_id_raises_clearly():
    http = FakeHttpClient(responses=[ok({})])
    with pytest.raises(RuntimeError, match="generationId"):
        generator(http).generate(brief())


def test_card_count_is_configurable():
    http = FakeHttpClient(responses=[ok(started()), ok(status("completed"))])
    generator(http, num_cards=7).generate(brief())
    assert http.calls[0].json_body["numCards"] == 7


def test_an_http_failure_propagates_so_the_pipeline_records_it():
    class Boom:
        def request(self, *a, **k):
            raise HttpError(402, "POST", "https://x", b"payment required")

    with pytest.raises(HttpError):
        GammaDeckGenerator("key", http=Boom()).generate(brief())
