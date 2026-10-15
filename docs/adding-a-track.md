# Adding a fourth kind of resource

Say you want to send a personalised PDF teardown. Four steps, no pipeline
change.

## 1. Add the track

In `src/followups/domain/models.py`:

```python
class Track(str, Enum):
    ...
    TEARDOWN = "TEARDOWN"
```

`tests/test_models.py` will fail until you add it there too. That is the point:
the enum test is the inventory.

## 2. Write the generator

Anything with a `track` attribute and a `generate(brief) -> Asset` method
satisfies `AssetGenerator`. Subclass `_BaseMockGenerator` for the mock and
`RealAdapter` for the real one.

```python
class MockTeardownGenerator(_BaseMockGenerator):
    track = Track.TEARDOWN
    extension = "html"

    def _render(self, brief: AssetBrief) -> str:
        return ...
```

The contract tests in `tests/test_contracts.py` are parameterised over a list
of generator classes. Add yours to that list and it is tested like the others:
it must declare its track, produce a previewable asset, be deterministic, and
personalise with the company name.

## 3. Register it

In `src/followups/adapters/registry.py`, add it to `generators`, and add the
real one to `ALL_REAL_ADAPTERS` so the credential and "not in the default
registry" guards stay exhaustive.

## 4. Route something to it

In `config/routing.yaml`:

```yaml
OBJECTION: TEARDOWN
```

No code change. The loader validates the new value against the `Track` enum, so
a typo fails at startup.

## What you did not have to touch

`pipeline/daily.py`, the store, the CLI, the cadence rules, or the dashboard.
That is the return on the ports and adapters layout.
