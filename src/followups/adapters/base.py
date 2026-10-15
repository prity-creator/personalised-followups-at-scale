"""Shared machinery for the real adapters.

Real adapters are deliberately unimplemented in this prototype: the spec puts
live API calls out of scope so that a clone costs nothing to run. What they do
implement is the credential check, so that wiring one in without a key fails
immediately and with a message naming the variable to set.
"""

from __future__ import annotations

import os


class MissingCredentials(RuntimeError):
    """An adapter was constructed without the credential it needs."""


class RealAdapter:
    ENV_KEY: str = ""

    def __init__(self, api_key: str, **options: str) -> None:
        if not api_key:
            raise MissingCredentials(f"{self.ENV_KEY} is not set")
        self.api_key = api_key
        self.options = options

    @classmethod
    def from_env(cls) -> RealAdapter:
        value = os.environ.get(cls.ENV_KEY, "")
        if not value:
            raise MissingCredentials(
                f"{cls.ENV_KEY} is not set. Copy .env.example to .env and fill it in, "
                f"or keep using the mock adapters, which need no credentials."
            )
        return cls(value)

    def _not_implemented(self, endpoint: str, docs: str) -> NotImplementedError:
        return NotImplementedError(
            f"{type(self).__name__} would call {endpoint}. Live API calls are out of scope "
            f"for this prototype, which runs on mock adapters at zero cost. "
            f"Implement against {docs} to go live."
        )
