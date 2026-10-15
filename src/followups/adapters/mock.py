"""Deterministic mock adapters.

These are what make the prototype runnable, testable and free. Nothing here
opens a socket. Output is seeded from the reply id so two runs over the same
fixtures produce byte-identical results.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from followups.adapters.dashboard import render as render_dashboard
from followups.domain.models import (
    Asset,
    AssetBrief,
    Category,
    Classification,
    FollowUp,
    FollowUpRecord,
    Prospect,
    Reply,
    SendResult,
    Track,
)

# Ordered: the first group whose keyword appears wins. NOT_INTERESTED precedes
# INTERESTED because "not interested" contains "interested".
KEYWORD_GROUPS: list[tuple[Category, float, tuple[str, ...]]] = [
    (Category.NOT_INTERESTED, 0.92, ("not interested", "no thanks", "remove me", "unsubscribe", "stop contacting")),
    (Category.REFERRAL, 0.88, ("reach out to", "speak to", "not the right person", "better person", "my colleague", "forward this")),
    (Category.BOOK_CALL, 0.90, ("book a call", "schedule", "calendar", "happy to chat", "set up a call", "jump on a call")),
    (Category.OBJECTION, 0.85, ("too expensive", "no budget", "already use", "we have a", "not right now", "bad timing")),
    (Category.INTERESTED, 0.87, ("tell me more", "sounds good", "interested", "send me", "yes please", "looks useful")),
]

UNMATCHED_CONFIDENCE = 0.3


class FixtureInbox:
    """Reads replies from a JSON file instead of the HeyReach inbox.

    Also supplies the people, from the sibling prospects.json, so it satisfies
    the same contract as a real inbox which returns both in one payload.
    """

    def __init__(self, path: Path | str, prospects_path: Path | str | None = None) -> None:
        self.path = Path(path)
        self.prospects_path = (
            Path(prospects_path)
            if prospects_path is not None
            else self.path.parent / "prospects.json"
        )

    def fetch_prospects(self, since: datetime | None) -> list[Prospect]:
        if not self.prospects_path.is_file():
            return []
        return [Prospect(**item) for item in json.loads(self.prospects_path.read_text())]

    def fetch_replies(self, since: datetime | None) -> list[Reply]:
        raw = json.loads(self.path.read_text())
        replies = [
            Reply(
                id=item["id"],
                prospect_id=item["prospect_id"],
                text=item["text"],
                received_at=datetime.fromisoformat(item["received_at"]),
            )
            for item in raw
        ]
        if since is not None:
            replies = [r for r in replies if r.received_at > since]
        return sorted(replies, key=lambda r: r.received_at)


class FixtureProspects:
    """Reads the prospect list from a JSON file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def all(self) -> list[Prospect]:
        return [Prospect(**item) for item in json.loads(self.path.read_text())]


class KeywordClassifier:
    """Stands in for the Claude classifier.

    Same output shape, same confidence floor behaviour, no API call. The floor
    rewrite lives here so the pipeline inherits it from either implementation.
    """

    def __init__(self, confidence_floor: float = 0.6) -> None:
        self.confidence_floor = confidence_floor

    def classify(self, reply: Reply, prospect: Prospect) -> Classification:
        text = reply.text.lower()
        for category, confidence, keywords in KEYWORD_GROUPS:
            hit = next((k for k in keywords if k in text), None)
            if hit is not None:
                return self._apply_floor(Classification(category, confidence, (hit,)))
        return self._apply_floor(Classification(Category.UNCLEAR, UNMATCHED_CONFIDENCE, ()))

    def _apply_floor(self, classification: Classification) -> Classification:
        if classification.confidence < self.confidence_floor:
            return Classification(
                Category.UNCLEAR, classification.confidence, classification.signals
            )
        return classification


class _BaseMockGenerator:
    """Writes a small local preview file and returns a fake hosted url."""

    track: Track = Track.NONE
    extension = "html"

    def __init__(self, out_dir: Path | str) -> None:
        self.out_dir = Path(out_dir)

    def generate(self, brief: AssetBrief) -> Asset:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        slug = f"{self.track.value.lower()}-{brief.reply.id}"
        path = self.out_dir / f"{slug}.{self.extension}"
        path.write_text(self._render(brief))
        return Asset(
            track=self.track,
            url=f"https://mock.invalid/{self.track.value.lower()}/{slug}",
            title=self._title(brief),
            preview_path=str(path),
        )

    def _title(self, brief: AssetBrief) -> str:
        return f"{brief.prospect.company}: next steps"

    def _render(self, brief: AssetBrief) -> str:
        raise NotImplementedError


class MockDeckGenerator(_BaseMockGenerator):
    """Stands in for Gamma."""

    track = Track.DECK

    def _render(self, brief: AssetBrief) -> str:
        p = brief.prospect
        slides = [
            (f"For {html.escape(p.company)}", f"Prepared for {html.escape(p.name)}, {html.escape(p.role)}"),
            ("What you said", html.escape(brief.reply.text)),
            ("Where we would start", "Three things we would do in the first 30 days"),
            ("What it costs you to wait", "The cost of the status quo, in your numbers"),
            ("Next step", "A 20 minute call, no deck required"),
        ]
        body = "".join(
            f"<section><h2>{t}</h2><p>{b}</p></section>" for t, b in slides
        )
        return f"<!doctype html><meta charset=utf-8><title>{html.escape(self._title(brief))}</title>{body}"


class MockVideoGenerator(_BaseMockGenerator):
    """Stands in for HeyGen plus ElevenLabs."""

    track = Track.VIDEO

    def _render(self, brief: AssetBrief) -> str:
        p = brief.prospect
        script = (
            f"Hi {p.name}, thanks for coming back to me. You mentioned "
            f'"{brief.reply.text.strip()}". Here is the 40 second version of what '
            f"we would do for {p.company}, then you can decide if a call is worth it."
        )
        return (
            "<!doctype html><meta charset=utf-8><title>"
            f"{html.escape(self._title(brief))}</title>"
            f"<h1>Video script for {html.escape(p.company)}</h1>"
            f"<p>{html.escape(script)}</p>"
            "<p><em>Mock asset. The real generator renders this through HeyGen "
            "with an ElevenLabs voice.</em></p>"
        )


class MockVisualGenerator(_BaseMockGenerator):
    """Stands in for Gemini image generation."""

    track = Track.VISUAL
    extension = "svg"

    def _render(self, brief: AssetBrief) -> str:
        p = brief.prospect
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450" '
            'viewBox="0 0 800 450" role="img">'
            f"<title>One page for {html.escape(p.company)}</title>"
            '<rect width="800" height="450" fill="#F1EFE8"/>'
            f'<text x="48" y="110" font-family="sans-serif" font-size="34" fill="#2C2C2A">'
            f"{html.escape(p.company)}</text>"
            f'<text x="48" y="170" font-family="sans-serif" font-size="20" fill="#5F5E5A">'
            f"The objection, answered in one page</text>"
            f'<text x="48" y="240" font-family="sans-serif" font-size="18" fill="#444441">'
            f"{html.escape(brief.reply.text[:70])}</text>"
            "</svg>"
        )


class FileSender:
    """Stands in for the HeyReach send endpoint. Appends, never transmits."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def send(self, follow_up: FollowUp, reply: Reply | None = None) -> SendResult:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "follow_up_id": follow_up.id,
                "prospect_id": follow_up.prospect_id,
                "track": follow_up.track.value,
                "asset_url": follow_up.asset.url if follow_up.asset else "",
                "message": follow_up.message_text,
            }
        )
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return SendResult(ok=True, detail=f"written to {self.path.name}")


class HtmlDashboardSink:
    """Renders every follow-up as one local page, so the data has a face.

    This is the zero-account alternative to a CRM: one self-contained file,
    no server, no CDN, readable in a light or a dark colour scheme. The markup
    lives in dashboard.py; this class owns only where it is written.
    SheetsSink implements the same port against Google Sheets.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def sync(self, records: list[FollowUpRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            render_dashboard(records, base_dir=self.path.parent), encoding="utf-8"
        )
