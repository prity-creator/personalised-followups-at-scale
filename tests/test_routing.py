from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from followups.domain.models import Category, Track
from followups.domain.routing import DEFAULT_ROUTING_PATH, RoutingError, load_routing

FULL = {
    "INTERESTED": "DECK",
    "BOOK_CALL": "VIDEO",
    "OBJECTION": "VISUAL",
    "REFERRAL": "DECK",
    "NOT_INTERESTED": "NONE",
    "UNCLEAR": "NONE",
}


def write_yaml(tmp_path: Path, mapping: dict) -> Path:
    p = tmp_path / "routing.yaml"
    p.write_text(yaml.safe_dump(mapping))
    return p


def test_default_routing_sends_deck_to_interested():
    assert load_routing(DEFAULT_ROUTING_PATH)[Category.INTERESTED] is Track.DECK


def test_default_routing_covers_every_category():
    assert set(load_routing(DEFAULT_ROUTING_PATH)) == set(Category)


def test_missing_category_raises_naming_it(tmp_path):
    partial = {k: v for k, v in FULL.items() if k != "REFERRAL"}
    with pytest.raises(RoutingError, match="REFERRAL"):
        load_routing(write_yaml(tmp_path, partial))


def test_unknown_track_raises_naming_it(tmp_path):
    bad = dict(FULL, INTERESTED="PODCAST")
    with pytest.raises(RoutingError, match="PODCAST"):
        load_routing(write_yaml(tmp_path, bad))


def test_unknown_category_key_raises(tmp_path):
    bad = dict(FULL, MAYBE="DECK")
    with pytest.raises(RoutingError, match="MAYBE"):
        load_routing(write_yaml(tmp_path, bad))


def test_missing_file_raises(tmp_path):
    with pytest.raises(RoutingError, match="not found"):
        load_routing(tmp_path / "nope.yaml")
