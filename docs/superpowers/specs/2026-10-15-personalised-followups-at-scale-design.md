# Follow-ups Through Personalised Resources at Scale

Design document. Approved 2026-10-15.

## 1. Problem

Outbound LinkedIn campaigns run through HeyReach produce a stream of replies.
Most of that reply volume dies in the inbox. The rep reads a reply, means to
follow up with something useful, and never does, because producing something
worth sending costs more time than the reply is worth in isolation.

The replies are not uniform. Someone saying "send me more" wants a different
artefact than someone saying "we already use a vendor" or "can we talk Tuesday".
A single generic follow-up template serves none of them well.

## 2. What this system does

Once a day it reads new replies, decides what each one is, decides which kind of
personalised resource fits that category, produces that resource, parks it in an
approval queue, and on approval sends it back through HeyReach.

Three kinds of resource:

- a slide deck, generated through Gamma
- a short personalised video, generated through HeyGen with an ElevenLabs voice
- a single page visual: a meme, an infographic, or a one page graphic, through Gemini

## 3. Scope

This repository is a **prototype**. It is built to be read, run offline, and
presented. It is not deployed and it does not hold credentials.

### In scope

- The full architecture, with every seam that a production version needs
- The domain core: categories, the routing table, the cadence rules
- A working end to end pipeline that runs on fixture data with mock adapters
- The Gamma deck track, specified in full
- SQLite persistence and the approval queue
- A generated HTML dashboard and a Google Sheets sink
- Tests, a CLI, a scheduled workflow, and a Claude Code skill

### Out of scope

- Live calls to any paid API. Every external adapter ships as a mock.
  Real implementations are described and left as documented stubs.
- A web UI, authentication, multi tenancy, or any datastore beyond SQLite
- Deployment

### Cost constraint

Running `pytest` and `followups run` on a fresh clone must perform zero network
calls and cost zero. This is a hard requirement, not a default. It is enforced
by a test that fails if the default adapter registry resolves to anything other
than mocks.

## 4. Architecture

Ports and adapters. The core is pure Python with no I/O. Everything that talks
to the outside world sits behind a narrow interface, and each interface has at
least two implementations, one real and one mock, which share a contract test.

```
                   +---------------------------+
                   |      pipeline/daily       |
                   +---------------------------+
                                 |
         +-----------+-----------+-----------+-----------+
         |           |           |           |           |
    InboxSource  Classifier  AssetGenerator  Sender    CrmSink
         |           |           |           |           |
     heyreach     claude      gamma /      heyreach   sheets /
      / mock      / mock    heygen / gemini  / mock     html
```

The core (`domain/`) imports nothing from `adapters/`. Dependencies point
inward. This is what makes the cadence and routing logic testable without a
network, and it is what lets the video and meme tracks ship as mocks today and
become real later without the pipeline changing.

## 5. Domain model

| Type | Meaning |
|---|---|
| `Prospect` | A person in a campaign: id, name, company, role, linkedin url |
| `Reply` | One inbound message: prospect id, text, received timestamp |
| `Category` | The classification of a reply, see section 6 |
| `Classification` | Category, confidence, and extracted signals |
| `Track` | Which resource to produce: DECK, VIDEO, VISUAL, NONE |
| `Asset` | A produced resource: track, url, title, local preview path |
| `FollowUp` | A queued send: prospect, asset, message text, state |
| `FollowUpState` | PENDING, APPROVED, REJECTED, SENT, FAILED, SKIPPED |

All of these are frozen dataclasses. They carry no behaviour that touches I/O.

## 6. Categories

Six categories, chosen so that every reply lands in exactly one.

| Category | Meaning |
|---|---|
| `INTERESTED` | Positive signal, wants to know more |
| `BOOK_CALL` | Explicitly asking to meet or proposing a time |
| `OBJECTION` | Engaged but pushing back: price, timing, incumbent vendor |
| `NOT_INTERESTED` | Clear no |
| `REFERRAL` | Pointing at a colleague as the right person |
| `UNCLEAR` | Anything the classifier is not confident about |

`UNCLEAR` exists so the classifier is never forced into a guess. A confidence
below the configured floor is rewritten to `UNCLEAR` regardless of what the
model returned, and `UNCLEAR` routes to `NONE`, which means a human looks at it.

## 7. Routing

Routing is **data, not code**. `config/routing.yaml` maps category to track:

```yaml
INTERESTED:     DECK
BOOK_CALL:      VIDEO
OBJECTION:      VISUAL
REFERRAL:       DECK
NOT_INTERESTED: NONE
UNCLEAR:        NONE
```

The original brief was self contradictory about whether a positive reply or a
negative reply should receive the deck. Making this a config file resolves that
permanently: the mapping is one edit, never a code change. The default above
follows the stated primary use case, a positive reply receives the deck.

The loader validates that every `Category` has an entry and that every value is
a known `Track`, and fails loudly at startup otherwise.

## 8. Cadence rules

Pure functions over timestamps, in `domain/cadence.py`. These are the rules that
stop the system embarrassing the user, so they carry the heaviest test coverage.

1. **Never repeat a track.** A prospect receives any given track at most once.
2. **Minimum gap.** No two follow-ups to the same prospect inside
   `min_gap_hours`, default 48.
3. **Silence timeout.** A prospect who has received a follow-up and has not
   replied within `silence_days`, default 3, becomes dormant and is excluded
   from all future runs.
4. **Max touches.** A hard ceiling of `max_touches`, default 3, per prospect.
5. **Open queue block.** A prospect with a follow-up already PENDING or APPROVED
   does not get another one queued.

Each rule is a predicate returning a `CadenceDecision` carrying an allow flag
and a human readable reason. Skips are recorded with their reason, so the
dashboard can answer "why did this person get nothing today".

## 9. Ports

```python
class InboxSource(Protocol):
    def fetch_replies(self, since: datetime) -> list[Reply]: ...

class Classifier(Protocol):
    def classify(self, reply: Reply, prospect: Prospect) -> Classification: ...

class AssetGenerator(Protocol):
    track: Track
    def generate(self, brief: AssetBrief) -> Asset: ...

class Sender(Protocol):
    def send(self, follow_up: FollowUp) -> SendResult: ...

class CrmSink(Protocol):
    def sync(self, records: list[FollowUpRecord]) -> None: ...
```

## 10. Adapters

| Port | Real | Mock |
|---|---|---|
| InboxSource | HeyReach REST, `GET /inbox/messages` | Reads `fixtures/replies.json` |
| Classifier | Claude API, structured output, strict schema | Keyword rules over the same schema |
| AssetGenerator DECK | Gamma generate API, polls for completion | Writes a local HTML deck preview |
| AssetGenerator VIDEO | HeyGen video plus ElevenLabs voice, documented stub | Returns a placeholder asset |
| AssetGenerator VISUAL | Gemini image generation, documented stub | Writes a local SVG card |
| Sender | HeyReach `POST /inbox/send` | Appends to `outbox.jsonl` |
| CrmSink | Google Sheets append | Generates `dashboard.html` |

Mocks are deterministic, seeded from the reply id, so test output is stable.

Both implementations of each port run against one shared contract test, so a
mock cannot drift from the interface its real counterpart satisfies.

## 11. Storage

SQLite at `data/followups.db`, created by migration on first run.

```sql
prospects(id TEXT PRIMARY KEY, name, company, role, linkedin_url, created_at)
replies(id TEXT PRIMARY KEY, prospect_id, text, received_at, ingested_at)
classifications(reply_id TEXT PRIMARY KEY, category, confidence, signals_json)
follow_ups(id TEXT PRIMARY KEY, prospect_id, reply_id, track, asset_url,
           asset_title, message_text, state, reason, created_at,
           decided_at, sent_at)
runs(id TEXT PRIMARY KEY, started_at, finished_at, counts_json)
```

`replies.id` is the provider message id, so re-ingesting the same reply is a
no-op. Idempotency is a property of the schema, not of the pipeline code.

## 12. Pipeline

`pipeline/daily.py`, seven stages, each a pure function of its input plus one
port call:

1. **Ingest.** `InboxSource.fetch_replies(since=last_run)`, upsert.
2. **Classify.** Unclassified replies only. Low confidence becomes `UNCLEAR`.
3. **Route and gate.** Apply the routing table, then the cadence rules.
   Skips are persisted with reasons.
4. **Generate.** Call the generator registered for the track. Build the brief
   from prospect, reply and classification signals.
5. **Queue.** Insert a `FollowUp` as PENDING.
6. **Send.** APPROVED rows only. Dry run unless `LIVE_SEND=true`.
7. **Mirror.** Push every record to the configured `CrmSink`.

A run is wrapped in a transaction per stage, so a failure part way through
leaves the database consistent and the next run resumes.

## 13. Safety

Three independent conditions must all hold before a message reaches a real
person: a real `Sender` adapter must be configured, `LIVE_SEND` must be `true`,
and the follow-up must be in state APPROVED. The default configuration fails all
three. The mock sender writes to `outbox.jsonl` and nothing else.

## 14. CLI

```
followups run            # one pipeline pass
followups review         # list pending, approve or reject interactively
followups approve <id>   # approve one
followups dashboard      # regenerate dashboard.html
followups seed           # load fixtures into a fresh database
```

## 15. Scheduling

- `.github/workflows/ci.yml`: tests on push, runs on mocks, no secrets.
- `.github/workflows/daily.yml`: cron, `workflow_dispatch` only by default so a
  fork never fires it unattended.
- `.claude/skills/daily-followups/SKILL.md`: drives the CLI conversationally.

## 16. Configuration

`config/settings.yaml` for behaviour, `.env` for credentials, `.env.example`
committed with placeholder values and a comment per key naming the provider and
where to obtain it. `.env` is gitignored. No real key is ever committed, and the
README states that the prototype runs fully without any of them.

## 17. Testing

- `domain/` reaches high coverage through table driven tests. Cadence and
  routing are tested exhaustively, including every skip reason.
- One contract test per port, parameterised over real and mock implementations.
  Real implementations are skipped without credentials.
- One end to end test asserting that a fixture run produces the expected queue.
- One guard test asserting the default registry is all mocks, which is what
  enforces the zero cost constraint.

## 18. Repository layout

```
personalised-followups-at-scale/
  README.md
  .env.example
  .gitignore
  pyproject.toml
  config/           routing.yaml, settings.yaml
  fixtures/         replies.json, prospects.json
  docs/             architecture.md, mindmap.md, adding-a-track.md
  src/followups/
    domain/         models, categories, routing, cadence
    ports/          protocols
    adapters/       heyreach, claude, gamma, heygen, gemini, crm
    store/          schema, repository
    pipeline/       daily
    cli.py
  tests/
  .github/workflows/
  .claude/skills/
```

## 19. Decisions this document settles

| Question | Decision |
|---|---|
| Runtime | Python core, Claude Code skill layer, Actions cron |
| Autonomy | Approval queue, auto send built but off |
| State | SQLite, with CrmSink for presentation |
| Positive or negative gets the deck | Config, defaulting to positive |
| Cost | Zero, mocks by default, enforced by test |
