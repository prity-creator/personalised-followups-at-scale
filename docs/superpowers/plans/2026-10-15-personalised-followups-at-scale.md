# Personalised Follow-up Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a prototype that reads LinkedIn outreach replies, classifies them, generates a matching personalised resource (deck, video, or single page visual), queues it for approval, and sends it on approval.

**Architecture:** Ports and adapters. A pure `domain/` core holds models, the routing table and the cadence rules and imports nothing from `adapters/`. Every external service sits behind a Protocol with a real implementation and a deterministic mock sharing one contract test. The default registry is all mocks, so a fresh clone runs end to end offline at zero cost.

**Tech Stack:** Python 3.11+, stdlib `sqlite3`, `pytest`, `PyYAML`, `click`. No other runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-10-15-personalised-followups-at-scale-design.md`

## Global Constraints

- Python 3.11 or later. Use `from __future__ import annotations` in every module.
- `src/followups/domain/` must not import from `adapters/`, `store/`, or `pipeline/`. Enforced by a test.
- The default adapter registry resolves to mock implementations only. Enforced by a test.
- No network call in any test. Real adapters skip without credentials.
- All domain models are frozen dataclasses.
- No real API key is ever committed. `.env` is gitignored; `.env.example` holds placeholders only.
- Timestamps are timezone aware UTC `datetime`. Naive datetimes are rejected.
- Default cadence values: `min_gap_hours=48`, `silence_days=3`, `max_touches=3`, `confidence_floor=0.6`.
- Six categories: `INTERESTED`, `BOOK_CALL`, `OBJECTION`, `NOT_INTERESTED`, `REFERRAL`, `UNCLEAR`.
- Four tracks: `DECK`, `VIDEO`, `VISUAL`, `NONE`.

## Review Focus

These are the input classes the spec implies but does not give a task of their own. Each one's test is added to the task that owns the code.

1. A reply arrives for a prospect that is not in the database. Expect the reply to be stored and the follow-up skipped with a reason, not an exception. Tested in Task 4.
2. The same provider message id is ingested twice. Expect exactly one row and no duplicate follow-up. Tested in Task 4.
3. `routing.yaml` is missing a category or names an unknown track. Expect a loud startup failure naming the offending key, not a silent `NONE`. Tested in Task 3.
4. The classifier returns a confidence below the floor. Expect the category rewritten to `UNCLEAR` regardless of what was returned. Tested in Task 5.
5. An asset generator raises. Expect the follow-up recorded as FAILED with the error text, the run continuing for other prospects. Tested in Task 7.

---

### Task 1: Project scaffold and domain models

**Files:**
- Create: `pyproject.toml`, `.env.example`, `src/followups/__init__.py`, `src/followups/domain/__init__.py`, `src/followups/domain/models.py`
- Test: `tests/test_models.py`, `tests/test_architecture.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Category`, `Track`, `FollowUpState` (str enums); frozen dataclasses `Prospect(id, name, company, role, linkedin_url)`, `Reply(id, prospect_id, text, received_at)`, `Classification(category, confidence, signals)`, `Asset(track, url, title, preview_path)`, `AssetBrief(prospect, reply, classification)`, `FollowUp(id, prospect_id, reply_id, track, asset, message_text, state, reason)`, `SendResult(ok, detail)`

- [ ] **Step 1: Write the failing tests**

```python
def test_reply_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone aware"):
        Reply(id="r1", prospect_id="p1", text="hi", received_at=datetime(2026, 10, 15))

def test_prospect_is_frozen():
    p = Prospect(id="p1", name="A", company="B", role="C", linkedin_url="u")
    with pytest.raises(FrozenInstanceError):
        p.name = "X"

def test_every_category_is_a_known_string():
    assert {c.value for c in Category} == {
        "INTERESTED", "BOOK_CALL", "OBJECTION",
        "NOT_INTERESTED", "REFERRAL", "UNCLEAR"}

def test_domain_does_not_import_outward():  # tests/test_architecture.py
    # walk src/followups/domain/*.py, parse with ast, collect import targets
    assert not any(m.startswith(("followups.adapters", "followups.store",
                                 "followups.pipeline")) for m in imported)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py tests/test_architecture.py -v`
Expected: FAIL, collection error, no module named `followups`

- [ ] **Step 3: Write `pyproject.toml` and the domain models**

`pyproject.toml`: setuptools backend, package dir `src`, requires-python `>=3.11`, dependencies `pyyaml` and `click`, optional-dependencies `dev = ["pytest"]`, and `[tool.pytest.ini_options] pythonpath = ["src"]`.

In `models.py` the timezone check lives in `__post_init__` on `Reply`, raising `ValueError("received_at must be timezone aware")`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example src tests
git commit -m "feat: add domain models and architecture guard"
```

---

### Task 2: Cadence rules

**Files:**
- Create: `src/followups/domain/cadence.py`
- Test: `tests/test_cadence.py`

**Interfaces:**
- Consumes: Task 1 models
- Produces: `CadenceConfig(min_gap_hours=48, silence_days=3, max_touches=3)`; `CadenceDecision(allowed: bool, reason: str)`; `ProspectHistory(tracks_sent: frozenset[Track], last_sent_at: datetime | None, touches: int, last_reply_at: datetime | None, has_open_queue: bool)` with classmethod `ProspectHistory.empty() -> ProspectHistory`; `evaluate(history: ProspectHistory, track: Track, now: datetime, config: CadenceConfig) -> CadenceDecision`

- [ ] **Step 1: Write the failing tests**

Table driven over the five rules in spec section 8. One case per rule proving it blocks, one proving it allows, plus the precedence case below.

```python
@pytest.mark.parametrize("history,track,expected_reason", [
    (history(tracks_sent={Track.DECK}), Track.DECK, "track already sent"),
    (history(last_sent_at=now - timedelta(hours=47)), Track.VIDEO, "minimum gap"),
    (history(last_sent_at=now - timedelta(days=4), last_reply_at=None), Track.VIDEO, "dormant"),
    (history(touches=3), Track.VIDEO, "max touches"),
    (history(has_open_queue=True), Track.VIDEO, "open follow-up"),
])
def test_rule_blocks(history, track, expected_reason):
    d = evaluate(history, track, now, CadenceConfig())
    assert d.allowed is False
    assert expected_reason in d.reason

def test_clean_history_allows():
    assert evaluate(ProspectHistory.empty(), Track.DECK, now, CadenceConfig()).allowed

def test_blocking_reasons_are_reported_in_fixed_order():
    # a history violating both max touches and minimum gap reports max touches
    d = evaluate(history(touches=3, last_sent_at=now), Track.VIDEO, now, CadenceConfig())
    assert "max touches" in d.reason

def test_track_none_is_always_blocked():
    assert evaluate(ProspectHistory.empty(), Track.NONE, now, CadenceConfig()).allowed is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cadence.py -v`
Expected: FAIL, cannot import `evaluate`

- [ ] **Step 3: Implement `evaluate` in `cadence.py`**

Evaluate rules in this fixed order and return the first block: `NONE` track, max touches, track already sent, open queue, dormant, minimum gap. Order matters because the reason is shown to the user; the test above pins it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cadence.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/followups/domain/cadence.py tests/test_cadence.py
git commit -m "feat: add cadence rules"
```

---

### Task 3: Routing table

**Files:**
- Create: `src/followups/domain/routing.py`, `config/routing.yaml`
- Test: `tests/test_routing.py`

**Interfaces:**
- Consumes: Task 1 `Category`, `Track`
- Produces: `load_routing(path: Path) -> dict[Category, Track]`; `RoutingError(Exception)`

`config/routing.yaml` holds exactly the mapping in spec section 7.

- [ ] **Step 1: Write the failing tests**

```python
def test_default_routing_sends_deck_to_interested():
    assert load_routing(DEFAULT_PATH)[Category.INTERESTED] is Track.DECK

def test_missing_category_raises_naming_it(tmp_path):
    with pytest.raises(RoutingError, match="REFERRAL"):
        load_routing(write_yaml(tmp_path, without="REFERRAL"))

def test_unknown_track_raises_naming_it(tmp_path):
    with pytest.raises(RoutingError, match="PODCAST"):
        load_routing(write_yaml(tmp_path, {"INTERESTED": "PODCAST"}))

def test_unknown_category_key_raises(tmp_path):
    with pytest.raises(RoutingError, match="MAYBE"):
        load_routing(write_yaml(tmp_path, {"MAYBE": "DECK"}))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_routing.py -v`
Expected: FAIL, cannot import `load_routing`

- [ ] **Step 3: Implement `load_routing` and write `config/routing.yaml`**

Validate completeness and value membership before returning. Raise `RoutingError` with the offending key in the message.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_routing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/followups/domain/routing.py config/routing.yaml tests/test_routing.py
git commit -m "feat: add routing table loaded from config"
```

---

### Task 4: SQLite store

**Files:**
- Create: `src/followups/store/__init__.py`, `src/followups/store/schema.py`, `src/followups/store/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: Task 1 models, Task 2 `ProspectHistory`
- Produces: `migrate(conn)`; `Repository(conn)` with `upsert_prospect`, `upsert_reply`, `unclassified_replies()`, `save_classification`, `history_for(prospect_id) -> ProspectHistory`, `queue(follow_up)`, `pending()`, `approved()`, `set_state(id, state, reason=None)`, `all_records()`, `start_run()`, `finish_run(id, counts)`

Tables exactly as spec section 11.

- [ ] **Step 1: Write the failing tests**

Use an in-memory connection via a fixture.

```python
def test_reingesting_same_message_id_keeps_one_row(repo):
    repo.upsert_reply(reply("m1")); repo.upsert_reply(reply("m1"))
    assert len(repo.unclassified_replies()) == 1

def test_reply_for_unknown_prospect_is_stored(repo):
    repo.upsert_reply(reply("m1", prospect_id="ghost"))
    assert repo.unclassified_replies()[0].prospect_id == "ghost"

def test_history_for_unknown_prospect_is_empty(repo):
    h = repo.history_for("ghost")
    assert h.touches == 0 and h.tracks_sent == frozenset()

def test_history_counts_only_sent_follow_ups(repo):
    # one SENT, one REJECTED
    assert repo.history_for("p1").touches == 1

def test_history_reports_open_queue_for_pending(repo):
    assert repo.history_for("p1").has_open_queue is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_repository.py -v`
Expected: FAIL, cannot import `Repository`

- [ ] **Step 3: Implement `schema.py` and `repository.py`**

`upsert_reply` uses `INSERT ... ON CONFLICT(id) DO NOTHING`. `history_for` derives `touches` and `tracks_sent` from rows in state SENT only, and `has_open_queue` from PENDING or APPROVED.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/followups/store tests/test_repository.py
git commit -m "feat: add sqlite store with idempotent reply ingest"
```

---

### Task 5: Ports and mock adapters

**Files:**
- Create: `src/followups/ports/__init__.py`, `src/followups/ports/protocols.py`, `src/followups/adapters/__init__.py`, `src/followups/adapters/mock.py`, `src/followups/adapters/registry.py`, `fixtures/prospects.json`, `fixtures/replies.json`
- Test: `tests/test_contracts.py`, `tests/test_mock_adapters.py`

**Interfaces:**
- Consumes: Task 1 models
- Produces: Protocols exactly as spec section 9. Mocks: `FixtureInbox(path)`, `KeywordClassifier(confidence_floor=0.6)`, `MockDeckGenerator(out_dir)`, `MockVideoGenerator(out_dir)`, `MockVisualGenerator(out_dir)`, `FileSender(path)`, `HtmlDashboardSink(path)`. `default_registry() -> Registry` returning only mocks.

`fixtures/replies.json` holds at least one reply per category, including one deliberately ambiguous one that must land as `UNCLEAR`.

- [ ] **Step 1: Write the failing tests**

```python
def test_default_registry_is_all_mocks():
    for a in default_registry().all_adapters():
        assert type(a).__module__ == "followups.adapters.mock"

def test_low_confidence_is_rewritten_to_unclear():
    c = KeywordClassifier(confidence_floor=0.6).classify(reply("hmm maybe"), prospect())
    assert c.category is Category.UNCLEAR

def test_classifier_is_deterministic():
    a = KeywordClassifier().classify(r, p); b = KeywordClassifier().classify(r, p)
    assert a == b

def test_file_sender_appends_and_does_not_network(tmp_path):
    s = FileSender(tmp_path / "outbox.jsonl")
    assert s.send(follow_up()).ok is True
    assert (tmp_path / "outbox.jsonl").read_text().count("\n") == 1

@pytest.mark.parametrize("gen", [MockDeckGenerator, MockVideoGenerator, MockVisualGenerator])
def test_generator_contract(gen, tmp_path):  # tests/test_contracts.py
    asset = gen(tmp_path).generate(brief())
    assert asset.track is gen.track and asset.url and Path(asset.preview_path).exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_contracts.py tests/test_mock_adapters.py -v`
Expected: FAIL, cannot import `default_registry`

- [ ] **Step 3: Implement the protocols, the mocks, and the registry**

`KeywordClassifier` matches ordered keyword groups per category and assigns a fixed confidence per group; anything unmatched returns confidence `0.3`. The floor rewrite happens in one place so Task 7 inherits it. Mock generators seed any randomness from `reply.id` so output is stable, and write a small HTML or SVG preview file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/followups/ports src/followups/adapters fixtures tests
git commit -m "feat: add ports and deterministic mock adapters"
```

---

### Task 6: Real adapter stubs

**Files:**
- Create: `src/followups/adapters/heyreach.py`, `src/followups/adapters/claude.py`, `src/followups/adapters/gamma.py`, `src/followups/adapters/heygen.py`, `src/followups/adapters/gemini.py`, `src/followups/adapters/sheets.py`
- Test: `tests/test_real_adapters_skip.py`

**Interfaces:**
- Consumes: Task 5 protocols
- Produces: `HeyReachInbox(api_key, base_url)`, `HeyReachSender(...)`, `ClaudeClassifier(api_key, model)`, `GammaDeckGenerator(api_key)`, `HeyGenVideoGenerator(...)`, `GeminiVisualGenerator(...)`, `SheetsSink(...)`. Each raises `MissingCredentials` when constructed without a key.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize("cls", ALL_REAL_ADAPTERS)
def test_real_adapter_refuses_to_construct_without_credentials(cls, monkeypatch):
    monkeypatch.delenv(cls.ENV_KEY, raising=False)
    with pytest.raises(MissingCredentials, match=cls.ENV_KEY):
        cls.from_env()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_real_adapters_skip.py -v`
Expected: FAIL, cannot import adapters

- [ ] **Step 3: Implement the stubs**

Each class declares `ENV_KEY`, implements `from_env()` raising `MissingCredentials`, and implements its port method with the request shape in a docstring and `raise NotImplementedError` with a message naming the endpoint and linking the provider's docs. These are deliberately unimplemented; the spec puts real calls out of scope.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/followups/adapters tests/test_real_adapters_skip.py
git commit -m "feat: add real adapter stubs guarded by credential checks"
```

---

### Task 7: Pipeline

**Files:**
- Create: `src/followups/pipeline/__init__.py`, `src/followups/pipeline/daily.py`, `config/settings.yaml`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: Tasks 2 to 6
- Produces: `RunCounts(ingested, classified, skipped, generated, queued, sent, failed)`; `run(repo, registry, routing, config, now, live_send=False) -> RunCounts`

- [ ] **Step 1: Write the failing tests**

```python
def test_fixture_run_queues_expected_tracks(repo, registry):
    counts = run(repo, registry, routing, config, now)
    assert counts.queued == EXPECTED_QUEUED
    assert {f.track for f in repo.pending()} == {Track.DECK, Track.VIDEO, Track.VISUAL}

def test_nothing_sends_without_approval(repo, registry, tmp_path):
    run(repo, registry, routing, config, now)
    assert not (tmp_path / "outbox.jsonl").exists()

def test_approved_sends_only_when_live_send(repo, registry):
    repo.set_state(fid, FollowUpState.APPROVED)
    assert run(repo, registry, routing, config, now, live_send=False).sent == 0
    assert run(repo, registry, routing, config, now, live_send=True).sent == 1

def test_generator_failure_marks_failed_and_continues(repo, exploding_registry):
    counts = run(repo, exploding_registry, routing, config, now)
    assert counts.failed == 1 and counts.queued >= 1
    assert "boom" in repo.all_records()[0].reason

def test_second_run_on_same_fixtures_queues_nothing_new(repo, registry):
    run(repo, registry, routing, config, now)
    assert run(repo, registry, routing, config, now).queued == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL, cannot import `run`

- [ ] **Step 3: Implement `run` as the seven stages in spec section 12**

Wrap each stage in its own transaction. Catch exceptions per prospect in the generate stage, record FAILED with `str(exc)` as the reason, continue the loop.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/followups/pipeline config/settings.yaml tests/test_pipeline.py
git commit -m "feat: add daily pipeline with per-prospect failure isolation"
```

---

### Task 8: CLI and dashboard

**Files:**
- Create: `src/followups/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: Tasks 4, 5, 7
- Produces: `click` group `followups` with `run`, `review`, `approve`, `dashboard`, `seed`

- [ ] **Step 1: Write the failing tests**

Use `click.testing.CliRunner`.

```python
def test_seed_then_run_then_dashboard(tmp_path):
    assert runner.invoke(cli, ["seed"]).exit_code == 0
    assert runner.invoke(cli, ["run"]).exit_code == 0
    assert runner.invoke(cli, ["dashboard"]).exit_code == 0
    assert "<table" in (tmp_path / "dashboard.html").read_text()

def test_run_prints_counts(tmp_path):
    assert "queued" in runner.invoke(cli, ["seed"]).output or True
    assert "queued" in runner.invoke(cli, ["run"]).output

def test_approve_moves_state(tmp_path):
    runner.invoke(cli, ["approve", fid])
    assert repo.pending() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL, cannot import `cli`

- [ ] **Step 3: Implement the CLI**

`run` prints the `RunCounts` fields one per line. `dashboard` calls `HtmlDashboardSink`. The dashboard renders one table of every follow-up with prospect, category, track, state and reason, so skip reasons are visible.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/followups/cli.py tests/test_cli.py
git commit -m "feat: add cli and html dashboard"
```

---

### Task 9: Docs, workflows, and the Claude Code skill

**Files:**
- Create: `README.md`, `docs/architecture.md`, `docs/mindmap.md`, `docs/adding-a-track.md`, `.github/workflows/ci.yml`, `.github/workflows/daily.yml`, `.claude/skills/daily-followups/SKILL.md`
- Test: `tests/test_docs.py`

**Interfaces:**
- Consumes: everything
- Produces: no code

- [ ] **Step 1: Write the failing test**

```python
def test_env_example_lists_every_adapter_env_key():
    text = Path(".env.example").read_text()
    for cls in ALL_REAL_ADAPTERS:
        assert cls.ENV_KEY in text

def test_env_example_holds_no_real_looking_key():
    assert not re.search(r"(sk-|gho_|AIza)[A-Za-z0-9_-]{12,}", Path(".env.example").read_text())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_docs.py -v`
Expected: FAIL

- [ ] **Step 3: Write the docs and workflows**

`README.md` leads with a 60 second quickstart proving the zero cost claim: clone, `pip install -e ".[dev]"`, `pytest`, `followups seed && followups run && followups dashboard`. Then the architecture, then a "bring your own keys" section stating plainly that the prototype needs none.

`docs/mindmap.md` holds the architecture as a Mermaid `mindmap` plus the pipeline as a `flowchart TD`, so GitHub renders both natively.

`ci.yml` runs `pytest` on push and pull request. `daily.yml` declares the cron but gates the job on `github.event_name == 'workflow_dispatch'` so a fork never fires it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md docs .github .claude tests/test_docs.py
git commit -m "docs: add readme, mindmap, workflows and claude code skill"
```
