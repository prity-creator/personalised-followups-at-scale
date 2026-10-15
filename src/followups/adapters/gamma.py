"""Gamma: turns a brief into a personalised slide deck."""

from __future__ import annotations

from followups.adapters.base import RealAdapter
from followups.domain.models import Asset, AssetBrief, Track

DOCS = "https://developers.gamma.app"


class GammaDeckGenerator(RealAdapter):
    """POST /generations then poll until the deck is ready, returning its share url."""

    ENV_KEY = "GAMMA_API_KEY"
    track = Track.DECK

    def generate(self, brief: AssetBrief) -> Asset:
        raise self._not_implemented("POST /v0.2/generations", DOCS)
