"""Google Gemini: a one page visual, meme or infographic answering an objection."""

from __future__ import annotations

from followups.adapters.base import RealAdapter
from followups.domain.models import Asset, AssetBrief, Track

DOCS = "https://ai.google.dev/gemini-api/docs/image-generation"


class GeminiVisualGenerator(RealAdapter):
    """Generate a single image sized for the LinkedIn inbox preview."""

    ENV_KEY = "GEMINI_API_KEY"
    track = Track.VISUAL

    def generate(self, brief: AssetBrief) -> Asset:
        raise self._not_implemented("POST /v1beta/models/{model}:generateContent", DOCS)
