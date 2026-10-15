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


def test_real_adapter_port_method_is_explicitly_unimplemented(monkeypatch):
    from followups.adapters.gamma import GammaDeckGenerator

    monkeypatch.setenv("GAMMA_API_KEY", "test-not-a-real-key")
    generator = GammaDeckGenerator.from_env()
    with pytest.raises(NotImplementedError, match="out of scope"):
        generator.generate(None)
