"""Gamma: turns a brief into a personalised slide deck.

Docs: https://developers.gamma.app

Generation is asynchronous: start one, then poll until it completes. The poll
budget is bounded so a stuck generation cannot hang the daily run, and `sleep`
is injected so the tests do not actually wait.
"""

from __future__ import annotations

import time
from typing import Callable

from followups.adapters.base import RealAdapter
from followups.domain.models import Asset, AssetBrief, Track

BASE_URL = "https://public-api.gamma.app/v1.0"
TERMINAL_FAILURES = {"failed", "error", "cancelled"}


class GammaDeckGenerator(RealAdapter):
    ENV_KEY = "GAMMA_API_KEY"
    track = Track.DECK

    def __init__(
        self,
        api_key: str,
        http=None,
        sleep: Callable[[float], None] = time.sleep,
        num_cards: int = 6,
        max_polls: int = 60,
        poll_seconds: float = 5.0,
        **options,
    ) -> None:
        super().__init__(api_key, http=http, **options)
        self._sleep = sleep
        self.num_cards = num_cards
        self.max_polls = max_polls
        self.poll_seconds = poll_seconds

    def generate(self, brief: AssetBrief) -> Asset:
        generation_id = self._start(brief)
        gamma_url = self._await_completion(generation_id)
        return Asset(
            track=Track.DECK,
            url=gamma_url,
            title=f"{brief.prospect.company}: next steps",
            preview_path="",
        )

    def _headers(self) -> dict[str, str]:
        return {"X-API-KEY": self.api_key}

    def _start(self, brief: AssetBrief) -> str:
        payload = self.http.request(
            "POST",
            f"{BASE_URL}/generations",
            headers=self._headers(),
            json_body={
                "inputText": self._prompt(brief),
                "textMode": "generate",
                "format": "presentation",
                "numCards": self.num_cards,
            },
        ).json()
        generation_id = payload.get("generationId")
        if not generation_id:
            raise RuntimeError(f"gamma did not return a generationId: {payload}")
        return generation_id

    def _await_completion(self, generation_id: str) -> str:
        for _ in range(self.max_polls):
            payload = self.http.request(
                "GET", f"{BASE_URL}/generations/{generation_id}", headers=self._headers()
            ).json()
            state = str(payload.get("status", "")).lower()

            if state == "completed":
                url = payload.get("gammaUrl") or payload.get("exportUrl")
                if not url:
                    raise RuntimeError(f"gamma completed without a url: {payload}")
                return url

            if state in TERMINAL_FAILURES:
                reason = (payload.get("error") or {}).get("message", state)
                raise RuntimeError(f"gamma generation failed: {reason}")

            self._sleep(self.poll_seconds)

        raise RuntimeError(
            f"gamma generation {generation_id} did not finish within "
            f"{self.max_polls} polls"
        )

    @staticmethod
    def _prompt(brief: AssetBrief) -> str:
        p = brief.prospect
        return (
            f"Create a short, specific sales deck for {p.name}, {p.role} at {p.company}.\n\n"
            f"They replied to a cold outreach message saying:\n"
            f'"{brief.reply.text}"\n\n'
            f"Their reply was classified as {brief.classification.category.value}.\n\n"
            f"Structure it as: what they said, what that usually means for a company like "
            f"{p.company}, the three things we would do in the first 30 days, what waiting "
            f"costs them, and a single clear next step. Be concrete and avoid generic "
            f"marketing language. Do not invent statistics or customer names."
        )
