"""The category to track routing table.

Routing is data, not code. The table lives in config/routing.yaml and is
validated on load, so a typo fails loudly at startup instead of silently
routing everything to NONE.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from followups.domain.models import Category, Track

DEFAULT_ROUTING_PATH = Path(__file__).resolve().parents[3] / "config" / "routing.yaml"


class RoutingError(Exception):
    """The routing table is missing, incomplete, or names something unknown."""


def load_routing(path: Path | str = DEFAULT_ROUTING_PATH) -> dict[Category, Track]:
    path = Path(path)
    if not path.is_file():
        raise RoutingError(f"routing table not found at {path}")

    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise RoutingError(f"routing table at {path} must be a mapping")

    known_categories = {c.value for c in Category}
    known_tracks = {t.value for t in Track}

    unknown_keys = sorted(set(map(str, raw)) - known_categories)
    if unknown_keys:
        raise RoutingError(f"unknown category in routing table: {', '.join(unknown_keys)}")

    missing = sorted(known_categories - set(map(str, raw)))
    if missing:
        raise RoutingError(f"routing table is missing a category: {', '.join(missing)}")

    table: dict[Category, Track] = {}
    for key, value in raw.items():
        if str(value) not in known_tracks:
            raise RoutingError(f"unknown track {value!r} for category {key}")
        table[Category(str(key))] = Track(str(value))
    return table
