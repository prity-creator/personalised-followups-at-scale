from __future__ import annotations

import pytest

from followups.adapters.base import MissingCredentials
from followups.adapters.registry import ALL_REAL_ADAPTERS, default_registry


@pytest.mark.parametrize("cls", ALL_REAL_ADAPTERS, ids=lambda c: c.__name__)
def test_real_adapter_refuses_to_construct_without_credentials(cls, monkeypatch):
    monkeypatch.delenv(cls.ENV_KEY, raising=False)
    with pytest.raises(MissingCredentials, match=cls.ENV_KEY):
        cls.from_env()


@pytest.mark.parametrize("cls", ALL_REAL_ADAPTERS, ids=lambda c: c.__name__)
def test_real_adapter_declares_an_env_key(cls):
    assert isinstance(cls.ENV_KEY, str) and cls.ENV_KEY


@pytest.mark.parametrize("cls", ALL_REAL_ADAPTERS, ids=lambda c: c.__name__)
def test_real_adapter_is_not_in_the_default_registry(cls, tmp_path):
    assert all(not isinstance(a, cls) for a in default_registry(tmp_path).all_adapters())


PORT_METHODS = {
    "HeyReachInbox": "fetch_replies",
    "HeyReachSender": "send",
    "ClaudeClassifier": "classify",
    "GammaDeckGenerator": "generate",
    "HeyGenVideoGenerator": "generate",
    "GeminiVisualGenerator": "generate",
    "SheetsSink": "sync",
    "ElevenLabsVoice": "synthesize",
}


@pytest.mark.parametrize("cls", ALL_REAL_ADAPTERS, ids=lambda c: c.__name__)
def test_real_adapter_implements_its_port_method(cls):
    """Every real adapter is implemented, not a stub that raises."""
    method = getattr(cls, PORT_METHODS[cls.__name__], None)
    assert callable(method), f"{cls.__name__} has no port method"


@pytest.mark.parametrize("cls", ALL_REAL_ADAPTERS, ids=lambda c: c.__name__)
def test_real_adapter_accepts_an_injected_http_client(cls):
    """Injection is what makes these testable without a socket or a bill."""
    from tests.fakes import FakeHttpClient

    # Adapters needing a second required argument get it here; the point of the
    # test is the injected client, not the constructor signature.
    extra = {"SheetsSink": {"spreadsheet_id": "sheet-1"}}.get(cls.__name__, {})
    fake = FakeHttpClient()
    assert cls("a-key", http=fake, **extra).http is fake
