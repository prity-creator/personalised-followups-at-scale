from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from followups.adapters.http import HttpError, HttpResponse, UrllibHttpClient


class FakeOpener:
    """Stands in for urllib.request.urlopen. No socket is ever opened."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeHttpResponse:
    def __init__(self, status=200, payload=None, headers=None):
        self.status = status
        self._body = json.dumps(payload if payload is not None else {}).encode()
        self.headers = headers or {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(status: int, body: bytes = b"{}") -> HTTPError:
    import io

    return HTTPError("https://x.invalid", status, "boom", {}, io.BytesIO(body))


def client(opener, **kw):
    return UrllibHttpClient(opener=opener, sleep=lambda _s: None, **kw)


def test_sends_method_url_and_json_body():
    opener = FakeOpener([FakeHttpResponse(payload={"ok": True})])
    client(opener).request(
        "POST", "https://api.invalid/x", headers={"X-Key": "k"}, json_body={"a": 1}
    )
    sent = opener.requests[0]
    assert sent.get_method() == "POST"
    assert sent.full_url == "https://api.invalid/x"
    assert json.loads(sent.data) == {"a": 1}
    assert sent.get_header("X-key") == "k"


def test_sets_json_content_type_only_when_there_is_a_body():
    opener = FakeOpener([FakeHttpResponse(), FakeHttpResponse()])
    c = client(opener)
    c.request("POST", "https://api.invalid/x", json_body={"a": 1})
    c.request("GET", "https://api.invalid/x")
    assert opener.requests[0].get_header("Content-type") == "application/json"
    assert opener.requests[1].get_header("Content-type") is None


def test_returns_a_parsed_response():
    opener = FakeOpener([FakeHttpResponse(payload={"id": "abc"})])
    response = client(opener).request("GET", "https://api.invalid/x")
    assert response.status == 200
    assert response.json()["id"] == "abc"


def test_retries_on_429_then_succeeds():
    opener = FakeOpener([http_error(429), FakeHttpResponse(payload={"id": "abc"})])
    assert client(opener).request("GET", "https://api.invalid/x").json()["id"] == "abc"
    assert len(opener.requests) == 2


def test_retries_on_500_then_succeeds():
    opener = FakeOpener([http_error(503), FakeHttpResponse(payload={"ok": 1})])
    assert client(opener).request("GET", "https://api.invalid/x").status == 200


def test_does_not_retry_a_client_error():
    opener = FakeOpener([http_error(400, b'{"error":"bad"}')])
    with pytest.raises(HttpError) as excinfo:
        client(opener).request("GET", "https://api.invalid/x")
    assert excinfo.value.status == 400
    assert len(opener.requests) == 1


def test_gives_up_after_max_attempts():
    opener = FakeOpener([http_error(500), http_error(500), http_error(500)])
    with pytest.raises(HttpError) as excinfo:
        client(opener, max_attempts=3).request("GET", "https://api.invalid/x")
    assert excinfo.value.status == 500
    assert len(opener.requests) == 3


def test_backoff_grows_between_attempts():
    slept: list[float] = []
    opener = FakeOpener([http_error(500), http_error(500), FakeHttpResponse()])
    UrllibHttpClient(opener=opener, sleep=slept.append, max_attempts=3).request(
        "GET", "https://api.invalid/x"
    )
    assert slept == sorted(slept) and len(slept) == 2 and slept[0] < slept[1]


def test_error_message_does_not_leak_the_api_key():
    opener = FakeOpener([http_error(401)])
    with pytest.raises(HttpError) as excinfo:
        client(opener).request(
            "GET", "https://api.invalid/x", headers={"Authorization": "Bearer sk-secret-value"}
        )
    assert "sk-secret-value" not in str(excinfo.value)


def test_non_json_body_is_available_as_bytes():
    response = HttpResponse(status=200, body=b"\x89PNG\r\n")
    assert response.body.startswith(b"\x89PNG")
    with pytest.raises(ValueError):
        response.json()
