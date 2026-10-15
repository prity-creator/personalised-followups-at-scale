"""Which adapter implementation each port resolves to.

The default registry is all mocks. That is the whole zero cost guarantee, and
a test asserts it, so wiring a real adapter in by accident fails the suite.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
