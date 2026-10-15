# Follow-ups Through Personalised Resources at Scale

Most replies to cold outreach die in the inbox. Not because nobody meant to
follow up, but because producing something worth sending costs more time than
any single reply seems to be worth.

This reads the replies, works out what each one is actually saying, and
produces a personalised resource that fits that specific answer:

| They said | They get |
|---|---|
| "tell me more" | a slide deck built for their company |
| "can we talk Tuesday?" | a 40 second personalised video |
| "too expensive" | a one page visual answering exactly that |
| "talk to my colleague" | a deck they can forward |
| "not interested" | nothing, and they stop being contacted |
| anything unclear | nothing, flagged for a human |

Nothing reaches a real person without a human approving it first.

## Run it in 60 seconds, with no API keys

This is the part worth checking before reading any code. **The whole pipeline
runs offline on fixture data with no API key and no account, at zero cost.**
Every external service sits behind a mock, and a test fails the build if a real
one sneaks into the default wiring.

```bash
git clone https://github.com/prity-creator/personalised-followups-at-scale
cd personalised-followups-at-scale
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                       # the full suite, no network
export FOLLOWUPS_HOME=./out
followups seed               # load six fixture prospects
followups run                # classify, route, generate, queue
followups review             # see what is waiting for you
open out/dashboard.html      # and what the whole queue looks like
```

A run prints what it did:

```
  ingested: 6
classified: 6
   skipped: 2      <- one "not interested", one too vague to call
 generated: 4
    queued: 4      <- waiting for you, not sent
      sent: 0
```

Approve one and send it:

```bash
followups approve <id>
followups run --live-send    # with mocks, "sending" appends to out/outbox.jsonl
```

## How it is put together

Ports and adapters. The core is pure Python that imports nothing from the
outside world, so the rules that decide who gets contacted are testable without
a network, and a test enforces that boundary by parsing every domain module.

```
ingest -> classify -> route and gate -> generate -> queue -> send -> mirror
```

- **Ingest** reads new replies. HeyReach in production, a JSON fixture here.
- **Classify** sorts a reply into six categories. Claude in production, keyword
  rules here. Below a confidence floor the answer becomes `UNCLEAR`, which
  routes to nothing, because a confident wrong guess is worse than no guess.
- **Route** maps category to resource using [`config/routing.yaml`](config/routing.yaml).
  This is data, not code: changing your mind about who gets a deck is one edit.
- **Gate** applies the cadence rules, which is the part that stops this
  embarrassing you. See below.
- **Generate** builds the resource. Gamma, HeyGen plus ElevenLabs, or Gemini in
  production; local HTML and SVG here.
- **Queue** parks it as `PENDING`. A human decides.
- **Send** only touches approved rows, and only with `--live-send`.
- **Mirror** writes the whole queue to a dashboard you can look at.

[`docs/architecture.md`](docs/architecture.md) has the detail,
[`docs/mindmap.md`](docs/mindmap.md) has it as a diagram.

## The cadence rules

These matter more than the generators. They are pure functions in
[`cadence.py`](src/followups/domain/cadence.py) and carry the heaviest tests.

1. A prospect never receives the same kind of resource twice.
2. No two follow-ups within 48 hours.
3. Silent for 3 days after a follow-up and they go dormant, permanently.
4. Three follow-ups per prospect, ever.
5. One open item in the queue at a time.

A reply that lands after the last send resets dormancy, so answering late does
not get someone dropped.

## Nothing sends by accident

Three independent conditions must all hold before a message reaches a person:

1. the follow-up is `APPROVED` by a human,
2. `--live-send` was passed,
3. a real sender adapter is configured.

A fresh clone fails all three. The mock sender appends to a file.

## Bring your own keys

The prototype needs none of this. To point it at real services, copy
[`.env.example`](.env.example) to `.env` and fill in the providers you want:
HeyReach, Anthropic, Gamma, HeyGen, ElevenLabs, Gemini, Google Sheets.

The real adapters in [`src/followups/adapters/`](src/followups/adapters/)
declare their endpoints and refuse to construct without a credential, but their
API calls are deliberately unimplemented: live calls are out of scope precisely
so this repository stays free to run. Each one names the endpoint and the docs
to implement against.

`.env` is gitignored, and a test fails the build if anything shaped like a real
key appears in `.env.example`.

## Why SQLite, and how to make it look like a CRM

SQLite is the source of truth: one file, no accounts, no rate limits, and the
dedupe and cadence rules become trivially testable. Presentation is a separate
port, `CrmSink`, so the same records can be pushed anywhere without the data
model following a vendor. Two sinks ship here, a generated HTML dashboard and a
Google Sheets stub. HubSpot or Airtable is one class implementing one method.

## Adding a fourth kind of resource

[`docs/adding-a-track.md`](docs/adding-a-track.md). It is four small steps and
no change to the pipeline.

## Layout

```
config/       routing.yaml, settings.yaml
fixtures/     sample prospects and replies
src/followups/
  domain/     models, routing, cadence   <- pure, no I/O, heavily tested
  ports/      the five interfaces
  adapters/   mock + real implementations of each
  store/      sqlite schema and repository
  pipeline/   the daily run
tests/        113 tests, none of which touch a network
docs/         architecture, mindmap, how to extend
```

## Status

Prototype. Built to be read and run. Not deployed, holds no credentials, and
makes no live API calls.
