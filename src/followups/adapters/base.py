"""Shared machinery for the real adapters.

Every real adapter takes an injected HTTP client. That is the single reason
these are testable: a test hands in a fake and asserts on the request that was
built, without a socket, a key, or a bill.

`from_env()` is the production path: it reads the credential and builds a real
client with retries. Constructing an adapter with no key fails immediately and
names the variable to set.
"""

from __future__ import annotations

import os

from followups.adapters.http import HttpClient, UrllibHttpClient


class MissingCredentials(RuntimeError):
    """An adapter was constructed without the credential it needs."""


class RealAdapter:
    ENV_KEY: str = ""
    #: Extra environment variables this adapter reads, name -> option key.
    EXTRA_ENV: dict[str, str] = {}

    def __init__(self, api_key: str, http: HttpClient | None = None, **options) -> None:
        if not api_key:
            raise MissingCredentials(
                f"{self.ENV_KEY} is not set. Copy .env.example to .env and fill it in, "
                f"or keep using the mock adapters, which need no credentials."
            )
        self.api_key = api_key
        self.http: HttpClient = http or UrllibHttpClient()
        self.options = options

    @classmethod
    def _require_env(cls, name: str) -> str:
        """Read one required environment variable or say which one is missing.

        Adapters that need more than one credential use this directly instead
        of the single-key path in from_env.
        """
        value = os.environ.get(name, "")
        if not value:
            raise MissingCredentials(
                f"{name} is not set. Copy .env.example to .env and fill it in, "
                f"or keep using the mock adapters, which need no credentials."
            )
        return value

    @classmethod
    def from_env(cls, http: HttpClient | None = None) -> RealAdapter:
        value = os.environ.get(cls.ENV_KEY, "")
        if not value:
            raise MissingCredentials(
                f"{cls.ENV_KEY} is not set. Copy .env.example to .env and fill it in, "
                f"or keep using the mock adapters, which need no credentials."
            )
        options = {
            option: os.environ[env_name]
            for env_name, option in cls.EXTRA_ENV.items()
            if os.environ.get(env_name)
        }
        return cls(value, http=http, **options)
