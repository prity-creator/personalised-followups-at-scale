"""The one place this project talks HTTP.

Every real adapter goes through this seam rather than calling urllib itself.
That buys three things: retries and backoff written once, credentials kept out
of error messages, and adapters that can be tested by injecting a fake client
instead of opening a socket.

Uses only the standard library, so installing this project pulls in no HTTP
dependency at all.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

# Headers whose values must never appear in an exception message or a log line.
SENSITIVE_HEADERS = frozenset(
    {"authorization", "x-api-key", "api-key", "x-goog-api-key", "x-api-keys"}
)

RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except json.JSONDecodeError as exc:
            raise ValueError(f"response body is not json: {exc}") from exc


class HttpError(RuntimeError):
    """A non-retryable response, or a retryable one that ran out of attempts.

    The message deliberately carries the method, url and status but never the
    request headers, because those hold the caller's API key.
    """

    def __init__(self, status: int, method: str, url: str, body: bytes) -> None:
        self.status = status
        self.method = method
        self.url = url
        self.body = body
        snippet = body[:400].decode("utf-8", "replace")
        super().__init__(f"{method} {url} failed with {status}: {snippet}")


class HttpClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: Any = None,
        timeout: float = 30.0,
    ) -> HttpResponse: ...


class UrllibHttpClient:
    """Standard library HTTP with bounded retries and exponential backoff.

    `opener` and `sleep` are injected so the retry logic can be tested without
    a socket and without actually waiting.
    """

    def __init__(
        self,
        opener: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
        backoff_seconds: float = 0.5,
    ) -> None:
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: Any = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        data = None
        all_headers = dict(headers or {})
        if json_body is not None:
            data = json.dumps(json_body).encode()
            all_headers.setdefault("Content-Type", "application/json")

        last_error: HttpError | None = None
        for attempt in range(1, self.max_attempts + 1):
            request = urllib.request.Request(url, data=data, headers=all_headers, method=method)
            try:
                with self._opener(request, timeout=timeout) as response:
                    return HttpResponse(
                        status=getattr(response, "status", 200),
                        body=response.read(),
                        headers={k.lower(): v for k, v in dict(response.headers).items()},
                    )
            except urllib.error.HTTPError as exc:
                body = exc.read() if hasattr(exc, "read") else b""
                last_error = HttpError(exc.code, method, url, body)
                if exc.code not in RETRY_STATUSES or attempt == self.max_attempts:
                    raise last_error from None
            except urllib.error.URLError as exc:
                last_error = HttpError(0, method, url, str(exc.reason).encode())
                if attempt == self.max_attempts:
                    raise last_error from None
            self._sleep(self.backoff_seconds * (2 ** (attempt - 1)))

        assert last_error is not None
        raise last_error


def redact(headers: dict[str, str]) -> dict[str, str]:
    """Headers safe to put in a log line."""
    return {
        k: ("<redacted>" if k.lower() in SENSITIVE_HEADERS else v) for k, v in headers.items()
    }
