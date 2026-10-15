from __future__ import annotations

from pathlib import Path

import pytest

from followups.adapters.claude import ClaudeClassifier
from followups.adapters.gamma import GammaDeckGenerator
from followups.adapters.heyreach import HeyReachInbox, HeyReachSender
from followups.adapters.mock import FixtureInbox
from followups.adapters.registry import FIXTURES_DIR, default_registry, live_registry
from followups.domain.models import Track

REAL_ENV = {
    "HEYREACH_API_KEY": "hr",
    "ANTHROPIC_API_KEY": "an",
    "GAMMA_API_KEY": "ga",
    "HEYGEN_API_KEY": "hg",
    "GEMINI_API_KEY": "ge",
}


def test_fixture_inbox_also_supplies_the_people():
    prospects = FixtureInbox(FIXTURES_DIR / "replies.json").fetch_prospects(since=None)
    assert len(prospects) == 6
    assert any(p.company == "Analytical Co" for p in prospects)


def test_live_registry_builds_real_adapters(tmp_path, monkeypatch):
    for key, value in REAL_ENV.items():
        monkeypatch.setenv(key, value)
    registry = live_registry(tmp_path)
    assert isinstance(registry.inbox, HeyReachInbox)
    assert isinstance(registry.classifier, ClaudeClassifier)
    assert isinstance(registry.sender, HeyReachSender)
    assert isinstance(registry.generators[Track.DECK], GammaDeckGenerator)


def test_live_registry_names_the_first_missing_credential(tmp_path, monkeypatch):
    from followups.adapters.base import MissingCredentials

    for key in REAL_ENV:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(MissingCredentials, match="HEYREACH_API_KEY"):
        live_registry(tmp_path)


def test_live_registry_falls_back_to_the_mock_sink_without_sheets(tmp_path, monkeypatch):
    for key, value in REAL_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS", raising=False)
    registry = live_registry(tmp_path)
    assert type(registry.crm_sink).__module__ in {
        "followups.adapters.mock",
        "followups.adapters.dashboard",
    }


def test_default_registry_is_still_all_mocks(tmp_path):
    for adapter in default_registry(tmp_path).all_adapters():
        assert type(adapter).__module__ in {
            "followups.adapters.mock",
            "followups.adapters.dashboard",
        }
