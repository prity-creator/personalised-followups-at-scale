# Deploying this for real

The repository runs on mocks out of the box and costs nothing. This page is
what you do when you want it talking to real services.

Work through it in order. Each step is runnable on its own, and you can stop at
any point and still have something useful.

## What it will cost

Be clear-eyed about this before you start.

| Service | What it does | Rough cost |
|---|---|---|
| HeyReach | reads replies, sends messages | paid plan, API included |
| Anthropic | classifies each reply | fractions of a cent per reply |
| Gamma | generates the deck | credits per deck, Pro plan or above |
| HeyGen | renders the video | credits per video, by the minute |
| ElevenLabs | optional, audio on its own | by the character |
| Gemini | generates the one page visual | per image, free tier available |
| Google Sheets | optional mirror | free |

The expensive ones are per asset, not per reply. Classification runs on every
reply; generation only runs on replies that pass the cadence rules. That
ordering is deliberate.

## Step 1: get the keys

Copy the template and fill in only what you need:

```bash
cp .env.example .env
```

| Variable | Where to get it | Needed for |
|---|---|---|
| `HEYREACH_API_KEY` | HeyReach, Settings, API | reading and sending |
| `ANTHROPIC_API_KEY` | console.anthropic.com | classification |
| `GAMMA_API_KEY` | Gamma, Settings and Members, API key tab | the deck track |
| `HEYGEN_API_KEY` | HeyGen, Settings, API | the video track |
| `GEMINI_API_KEY` | aistudio.google.com | the visual track |

`.env` is gitignored. Never commit it.

## Step 2: prove the keys work before spending anything

Run the suite. It still passes with no keys and makes no calls:

```bash
pytest
```

Then run one live pass with sending still off:

```bash
export FOLLOWUPS_HOME=./out
followups run --live
```

`--live` uses the real providers. It does **not** send anything. Sending needs
`--live-send` as well, and an approved follow-up. Those flags are separate on
purpose: `--live` spends money generating, `--live-send` puts a message in
front of a person, and you will often want the first without the second.

If a key is missing, the run stops immediately and names the variable rather
than half-finishing.

## Step 3: look at what it produced

```bash
followups review
followups dashboard && open out/dashboard.html
```

Read the actual decks and videos it generated. Read the messages it drafted.
The classifier will be wrong sometimes, and this is the moment to find out, not
after it has messaged forty people.

## Step 4: tune before you scale

Three dials, all config, no code:

- `config/routing.yaml` decides which category gets which resource.
- `config/settings.yaml` holds the cadence rules and the confidence floor.
- Raise the confidence floor if you see misclassifications. More replies will
  land in `UNCLEAR` and wait for you, which is the safe direction.

## Step 5: send, deliberately

Approve the ones you are happy with, then send:

```bash
followups approve <id>
followups run --live --live-send
```

Approve a handful first. Watch what the replies look like. Then widen.

## Step 6: put it on a schedule

The repository ships `.github/workflows/daily.yml` with the cron declared but
the job gated on a manual trigger, so a fork never fires it unattended.

To run it on schedule for real:

1. Add each key as a repository secret under Settings, Secrets and variables,
   Actions.
2. Map them to `env:` in the workflow.
3. Remove the `if: github.event_name == 'workflow_dispatch'` line.
4. Decide, on purpose, whether that scheduled job passes `--live-send`. Leaving
   it off means a human still approves every message, which is the recommended
   setup until the classifier has earned your trust.

Note that GitHub Actions runners are stateless. `followups.db` will not survive
between runs unless you persist it, so either commit it to a private branch,
upload and download it as an artifact, or point `FOLLOWUPS_HOME` at mounted
storage. Without that, the cadence rules lose their memory and people will be
contacted twice.

## Running it somewhere other than Actions

Any machine with Python 3.11 and a cron works:

```bash
pip install -e .
export FOLLOWUPS_HOME=/var/lib/followups
followups run --live
```

The only state is one SQLite file inside `FOLLOWUPS_HOME`. Back that up and you
have backed up the whole system.

## Verify these before trusting them

The adapters are written against each provider's published documentation, and
the request shapes are unit tested, but no live call has ever been made from
this repository. The first time you run `--live`, expect to adjust something.

| Adapter | Verify against |
|---|---|
| `heyreach.py` | https://docs.heyreach.io/hey-reach-api |
| `claude.py` | https://docs.anthropic.com/en/api/messages |
| `gamma.py` | https://developers.gamma.app |
| `heygen.py` | https://docs.heygen.com |
| `gemini.py` | https://ai.google.dev/gemini-api/docs |

If a provider has changed something, the fix is in one file, and the fake HTTP
client in `tests/fakes.py` lets you pin the new shape in a test first.
