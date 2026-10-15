"""Which adapter implementation each port resolves to.

The default registry is all mocks. That is the whole zero cost guarantee, and
a test asserts it, so wiring a real adapter in by accident fails the suite.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from followups.adapters.base import MissingCredentials
from followups.adapters.claude import ClaudeClassifier
from followups.adapters.gamma import GammaDeckGenerator
from followups.adapters.gemini import GeminiVisualGenerator
from followups.adapters.heygen import ElevenLabsVoice, HeyGenVideoGenerator
from followups.adapters.heyreach import HeyReachInbox, HeyReachSender
from followups.adapters.sheets import SheetsSink
from followups.adapters.mock import (
    FileSender,
    FixtureInbox,
    HtmlDashboardSink,
    KeywordClassifier,
    MockDeckGenerator,
    MockVideoGenerator,
    MockVisualGenerator,
)
from followups.domain.models import Track
from followups.ports.protocols import AssetGenerator, Classifier, CrmSink, InboxSource, Sender

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "fixtures"


@dataclass(frozen=True)
class Registry:
    inbox: InboxSource
    classifier: Classifier
    generators: dict[Track, AssetGenerator]
    sender: Sender
    crm_sink: CrmSink

    def all_adapters(self) -> list[object]:
        return [self.inbox, self.classifier, self.sender, self.crm_sink, *self.generators.values()]


def default_registry(home: Path | str) -> Registry:
    """Every port wired to its mock. No network, no credentials, no cost."""
    home = Path(home)
    assets = home / "assets"
    return Registry(
        inbox=FixtureInbox(FIXTURES_DIR / "replies.json"),
        classifier=KeywordClassifier(),
        generators={
            Track.DECK: MockDeckGenerator(assets),
            Track.VIDEO: MockVideoGenerator(assets),
            Track.VISUAL: MockVisualGenerator(assets),
        },
        sender=FileSender(home / "outbox.jsonl"),
        crm_sink=HtmlDashboardSink(home / "dashboard.html"),
    )


# Every real adapter, so the credential guard and the "not in the default
# registry" guard stay exhaustive as adapters are added.
ALL_REAL_ADAPTERS = [
    HeyReachInbox,
    HeyReachSender,
    ClaudeClassifier,
    GammaDeckGenerator,
    HeyGenVideoGenerator,
    ElevenLabsVoice,
    GeminiVisualGenerator,
    SheetsSink,
]


def live_registry(home: Path | str) -> Registry:
    """Every port wired to a real provider, built from environment variables.

    Nothing calls this by default. `followups run --live` does, and it raises
    MissingCredentials naming the first variable that is not set, rather than
    half-starting a run that cannot finish.

    The CRM sink is optional: without Google credentials the local dashboard is
    used, because presentation is not worth failing a run over.
    """
    home = Path(home)
    assets = home / "assets"

    inbox = HeyReachInbox.from_env()
    classifier = ClaudeClassifier.from_env()
    sender = HeyReachSender.from_env()
    deck = GammaDeckGenerator.from_env()
    video = HeyGenVideoGenerator.from_env()
    visual = GeminiVisualGenerator.from_env()
    visual.out_dir = assets

    try:
        crm_sink = SheetsSink.from_env()
    except MissingCredentials:
        crm_sink = HtmlDashboardSink(home / "dashboard.html")

    return Registry(
        inbox=inbox,
        classifier=classifier,
        generators={Track.DECK: deck, Track.VIDEO: video, Track.VISUAL: visual},
        sender=sender,
        crm_sink=crm_sink,
    )
