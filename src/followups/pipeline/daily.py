"""The daily run.

Seven stages, in order: ingest, classify, route and gate, generate, queue,
send, mirror. Each stage is a function of its input plus one port call, so the
whole thing can be exercised end to end against mocks.

Nothing here decides whether a message is appropriate. That is the routing
table and the cadence rules, both of which live in the domain core.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from followups.adapters.registry import Registry
from followups.domain.cadence import CadenceConfig, evaluate
from followups.domain.models import (
    AssetBrief,
    Category,
    FollowUp,
    FollowUpState,
    Track,
)


@dataclass
class RunCounts:
    ingested: int = 0
    classified: int = 0
    skipped: int = 0
    generated: int = 0
    queued: int = 0
    sent: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return self.__dict__.copy()


def _message_for(category: Category, prospect_name: str, asset_title: str) -> str:
    parts = prospect_name.split()
    first_name = parts[0] if parts else "there"
    openers = {
        Category.INTERESTED: "Glad it landed. I put this together for you:",
        Category.BOOK_CALL: "Before we talk, here is a 40 second version:",
        Category.OBJECTION: "Fair point. One page on exactly that:",
        Category.REFERRAL: "Thanks for pointing me in the right direction. Worth passing on:",
    }
    opener = openers.get(category, "Thought this might be useful:")
    return f"{first_name}, {opener} {asset_title}"


def _record_skip(repo, prospect_id: str, reply_id: str, track: Track, reason: str, now: datetime) -> None:
    repo.queue(
        FollowUp(
            id=str(uuid.uuid4()),
            prospect_id=prospect_id,
            reply_id=reply_id,
            track=track,
            asset=None,
            message_text="",
            state=FollowUpState.SKIPPED,
            reason=reason,
        ),
        now,
    )


def run(
    repo,
    registry: Registry,
    routing: dict[Category, Track],
    now: datetime,
    cadence: CadenceConfig | None = None,
    live_send: bool = False,
) -> RunCounts:
    cadence = cadence or CadenceConfig()
    counts = RunCounts()

    # Read the watermark before opening this run, or it would read itself.
    since = repo.last_run_started_at()
    run_id = repo.start_run(now)

    # 1. Ingest. Duplicate message ids are dropped by the schema, so an
    # overlapping window is harmless and the watermark is only an optimisation.
    for reply in registry.inbox.fetch_replies(since):
        repo.upsert_reply(reply, now)
        counts.ingested += 1

    # 2. Classify. Only replies that have never been classified.
    for reply in repo.unclassified_replies():
        prospect = repo.get_prospect(reply.prospect_id)
        classification = registry.classifier.classify(reply, prospect)
        repo.save_classification(reply.id, classification)
        counts.classified += 1

        # 3. Route and gate.
        track = routing.get(classification.category, Track.NONE)

        if prospect is None:
            counts.skipped += 1
            _record_skip(
                repo, reply.prospect_id, reply.id, track,
                f"unknown prospect {reply.prospect_id}", now,
            )
            continue

        decision = evaluate(repo.history_for(prospect.id), track, now, cadence)
        if not decision.allowed:
            counts.skipped += 1
            _record_skip(repo, prospect.id, reply.id, track, decision.reason, now)
            continue

        # 4. Generate. One prospect's failure must not end the run.
        generator = registry.generators.get(track)
        if generator is None:
            counts.skipped += 1
            _record_skip(repo, prospect.id, reply.id, track, f"no generator for {track.value}", now)
            continue

        follow_up_id = str(uuid.uuid4())
        try:
            asset = generator.generate(AssetBrief(prospect, reply, classification))
        except Exception as exc:  # noqa: BLE001 - isolation is the point
            counts.failed += 1
            repo.queue(
                FollowUp(
                    id=follow_up_id,
                    prospect_id=prospect.id,
                    reply_id=reply.id,
                    track=track,
                    asset=None,
                    message_text="",
                    state=FollowUpState.FAILED,
                    reason=f"generator failed: {exc}",
                ),
                now,
            )
            continue
        counts.generated += 1

        # 5. Queue, PENDING. A human decides next.
        repo.queue(
            FollowUp(
                id=follow_up_id,
                prospect_id=prospect.id,
                reply_id=reply.id,
                track=track,
                asset=asset,
                message_text=_message_for(classification.category, prospect.name, asset.title),
                state=FollowUpState.PENDING,
            ),
            now,
        )
        counts.queued += 1

    # 6. Send. Three conditions, all independent: approved, live, real sender.
    if live_send:
        for follow_up in repo.approved():
            result = registry.sender.send(follow_up)
            if result.ok:
                repo.set_state(follow_up.id, FollowUpState.SENT, sent_at=now)
                counts.sent += 1
            else:
                repo.set_state(follow_up.id, FollowUpState.FAILED, reason=result.detail)
                counts.failed += 1

    # 7. Mirror.
    registry.crm_sink.sync(repo.all_records())
    repo.finish_run(run_id, counts.as_dict(), now)
    return counts
