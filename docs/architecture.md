# Architecture

## The shape

Ports and adapters, with dependencies pointing inward.

```
                        pipeline/daily.py
                               |
      +----------+-------------+-------------+----------+
      |          |             |             |          |
 InboxSource Classifier  AssetGenerator    Sender    CrmSink
      |          |             |             |          |
  heyreach    claude     gamma/heygen/     heyreach   sheets
   / mock     / mock      gemini / mock     / mock    / html
```

`src/followups/domain/` imports nothing from `adapters/`, `store/`,
`pipeline/` or `cli.py`. `tests/test_architecture.py` parses every domain
module with `ast` and fails if that is ever violated.

That boundary is not decoration. It is what lets the rules that decide whether
a real person gets contacted be tested exhaustively, in milliseconds, with no
network and no credentials.

## Why each port exists

| Port | Why it is a seam |
|---|---|
| `InboxSource` | The reply source is the thing most likely to change (HeyReach today, something else later). Fixtures make the pipeline testable. |
| `Classifier` | Swapping models, or falling back to rules when the API is down, must not touch the pipeline. |
| `AssetGenerator` | Three implementations today and a fourth is expected. Each is a different vendor with a different failure mode. |
| `Sender` | The only component that can do something irreversible. Isolating it is what makes "nothing sends by accident" checkable. |
| `CrmSink` | Presentation should never own the data model. SQLite stays the truth. |

## The confidence floor

The classifier returns a category and a confidence. Below the floor the
category is rewritten to `UNCLEAR` regardless of what came back, and `UNCLEAR`
routes to no resource at all.

This lives inside the classifier rather than the pipeline, so both the real and
the mock implementation inherit it and cannot disagree.

A confident wrong classification sends the wrong artefact to a real prospect
under the operator's name. An `UNCLEAR` costs one human glance. The asymmetry
is the whole argument.

## Failure isolation

Asset generation is the stage most likely to fail: three third-party vendors,
each with its own outage. A generator that raises marks that one follow-up
`FAILED` with the error text and the loop continues.

One vendor having a bad morning must not cost every other prospect their
follow-up.

## Idempotency

`replies.id` is the provider's own message id and the table's primary key, so
re-ingesting a reply the system has already seen is a no-op at the database
level, not a guard the pipeline has to remember. The run also keeps a
watermark, but that is only an optimisation; correctness comes from the schema.

## Where the decisions live

| Decision | Where | Change it by |
|---|---|---|
| Who gets which resource | `config/routing.yaml` | editing one line |
| How often anyone is contacted | `config/settings.yaml` | editing one line |
| What a resource looks like | an `AssetGenerator` | writing one class |
| Where the records are shown | a `CrmSink` | writing one class |
| Whether anything sends | three independent conditions | all three, deliberately |
