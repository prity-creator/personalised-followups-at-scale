from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from followups.adapters.mock import FixtureProspects
from followups.adapters.registry import default_registry
from followups.domain.models import Category, FollowUpState, Track
from followups.domain.routing import load_routing
from followups.pipeline.daily import run
from tests.conftest import NOW

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ROUTING = load_routing()


@pytest.fixture()
def registry(tmp_path):
    return default_registry(tmp_path)


@pytest.fixture()
def seeded(repo):
    for prospect in FixtureProspects(FIXTURES / "prospects.json").all():
        repo.upsert_prospect(prospect, NOW)
    return repo


def test_fixture_run_queues_one_per_routed_category(seeded, registry):
    counts = run(seeded, registry, ROUTING, now=NOW)
    assert counts.ingested == 6
    assert counts.classified == 6
    # NOT_INTERESTED and UNCLEAR route to NONE, so four of six are queued
    assert counts.queued == 4
    assert {f.track for f in seeded.pending()} == {Track.DECK, Track.VIDEO, Track.VISUAL}


def test_unrouted_categories_are_skipped_with_a_reason(seeded, registry):
    run(seeded, registry, ROUTING, now=NOW)
    skipped = [r for r in seeded.all_records() if r.state is FollowUpState.SKIPPED]
    assert len(skipped) == 2
    assert all("no track routed" in r.reason for r in skipped)


def test_nothing_sends_without_approval(seeded, registry, tmp_path):
    run(seeded, registry, ROUTING, now=NOW)
    assert not (tmp_path / "outbox.jsonl").exists()


def test_approved_sends_only_when_live_send(seeded, registry):
    run(seeded, registry, ROUTING, now=NOW)
    target = seeded.pending()[0]
    seeded.set_state(target.id, FollowUpState.APPROVED)

    later = NOW + timedelta(days=1)
    assert run(seeded, registry, ROUTING, now=later, live_send=False).sent == 0
    assert run(seeded, registry, ROUTING, now=later, live_send=True).sent == 1


def test_generator_failure_marks_failed_and_continues(seeded, registry):
    class Exploding:
        track = Track.DECK

        def generate(self, brief):
            raise RuntimeError("boom")

    broken = replace(registry, generators={**registry.generators, Track.DECK: Exploding()})
    counts = run(seeded, broken, ROUTING, now=NOW)

    assert counts.failed == 2  # two replies route to DECK
    assert counts.queued == 2  # video and visual still got through
    failed = [r for r in seeded.all_records() if r.state is FollowUpState.FAILED]
    assert all("boom" in r.reason for r in failed)


def test_second_run_on_same_fixtures_queues_nothing_new(seeded, registry):
    run(seeded, registry, ROUTING, now=NOW)
    assert run(seeded, registry, ROUTING, now=NOW + timedelta(minutes=1)).queued == 0


def test_cadence_blocks_a_second_queue_while_one_is_open(seeded, registry):
    run(seeded, registry, ROUTING, now=NOW)
    before = len(seeded.pending())
    run(seeded, registry, ROUTING, now=NOW + timedelta(days=1))
    assert len(seeded.pending()) == before


def test_reply_from_an_unknown_prospect_is_skipped_not_crashed(repo, registry):
    # no prospects seeded at all
    counts = run(repo, registry, ROUTING, now=NOW)
    assert counts.ingested == 6
    assert counts.queued == 0
    assert all("unknown prospect" in r.reason for r in repo.all_records())


def test_run_mirrors_to_the_crm_sink(seeded, registry, tmp_path):
    run(seeded, registry, ROUTING, now=NOW)
    assert "<table" in (tmp_path / "dashboard.html").read_text()


def test_message_survives_a_blank_prospect_name():
    """A whitespace-only name must not crash the message builder.

    Found during final review: `name.split()[0]` raises IndexError on " ",
    which is truthy, so the falsy guard does not catch it.
    """
    from followups.pipeline.daily import _message_for

    assert _message_for(Category.INTERESTED, "   ", "A deck").startswith("there,")
