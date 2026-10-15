"""Test doubles. Never imported by production code."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from followups.adapters.http import HttpResponse


@dataclass
class RecordedCall:
    method: str
    url: str
    headers: dict[str, str]
    json_body: Any


@dataclass
class FakeHttpClient:
    """Returns queued responses and records every call made against it."""

    responses: list[HttpResponse] = field(default_factory=list)
    calls: list[RecordedCall] = field(default_factory=list)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: Any = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        self.calls.append(RecordedCall(method, url, dict(headers or {}), json_body))
        if not self.responses:
            raise AssertionError(f"FakeHttpClient had no queued response for {method} {url}")
        return self.responses.pop(0)


def ok(payload: Any, status: int = 200) -> HttpResponse:
    return HttpResponse(status=status, body=json.dumps(payload).encode())


def raw(body: bytes, status: int = 200, content_type: str = "application/octet-stream") -> HttpResponse:
    return HttpResponse(status=status, body=body, headers={"content-type": content_type})
