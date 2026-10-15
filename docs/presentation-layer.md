# The presentation layer

SQLite is the source of truth. Everything in this document is a mirror of it,
which is why `CrmSink` is one way: a sink is told what the database says and
never tells the database anything back.

```python
class CrmSink(Protocol):
    def sync(self, records: list[FollowUpRecord]) -> None: ...
```

Two implementations ship. A third, HubSpot or Airtable or whatever the operator
already pays for, is one class with one method.

## FollowUpRecord

One flattened row, holding everything a surface needs to show a follow-up
without querying anything else:

| Field | Comes from |
|---|---|
| `follow_up_id`, `state`, `reason`, `track`, `created_at` | `follow_ups` |
| `prospect_name`, `company`, `role` | `prospects` |
| `category`, `confidence` | `classifications` |
| `reply_text` | `replies`, the thing the prospect actually wrote |
| `message_text` | the draft waiting to go back |
| `asset_title`, `asset_url`, `asset_preview_path` | the generated resource |

Every field after `created_at` carries a default, so a sink written against an
earlier shape still constructs. Add a field here rather than teaching each sink
to run its own query.

## The dashboard

`HtmlDashboardSink` writes one file. The markup lives in
[`adapters/dashboard.py`](../src/followups/adapters/dashboard.py); the sink
class owns only where the file is written.

It is deliberately self-contained: no server, no build step, nothing fetched
from a CDN, and the colours are defined twice so it reads correctly whether the
reader's machine is set to light or dark. Open it from a file path, mail it to
someone, put it on a laptop with no network. It still works.

What it shows:

- **Tiles** for pending, sent, skipped and failed, the four numbers someone
  wants before they want any row.
- **Filter chips** for every track and every state actually present, each
  carrying its own count, plus a search box over names, companies and reply
  text. Filtering happens in the page, so there is nothing to rebuild.
- **One card per follow-up**, newest first, showing the reply the prospect
  sent, the message drafted back, the skip reason when there is one, and links
  to both the hosted asset and the local preview file.

### Rules the tests hold

Prospect-written text reaches this page, which makes it the one place in the
project where escaping is a safety property rather than a nicety:

1. Every interpolated value goes through `escape()`. A reply containing markup
   is shown as text, never parsed as markup.
2. Only `http`, `https` and `file` urls become links. Anything else is printed
   and not linked, so a bad record cannot produce a `javascript:` link.
3. The page opens exactly one `<script>`, its own.

### What real inbox data looks like

The fixtures are tidy. A live inbox is not, and the dashboard is written for
the untidy version:

| Case | What the page does |
|---|---|
| No prospect name | Falls back to "Unknown prospect" |
| No company or role | Drops the subtitle rather than printing a stray comma |
| No reply body | Says "No reply text recorded." instead of leaving a hollow card |
| A multi paragraph reply | Keeps the line breaks, via `white-space: pre-wrap` |
| A very long url | Wraps it inside the card, via `overflow-wrap: anywhere`, so the page never scrolls sideways |
| Confidence of 0 | Omits the badge rather than printing "0% sure" |

[`tests/test_dashboard.py`](../tests/test_dashboard.py) pins each of these.

## The Google Sheets sink

[`SheetsSink`](../src/followups/adapters/sheets.py) puts the same records in a
spreadsheet, for people who would rather filter in rows.

It clears the tab and rewrites it on every sync. Appending would be cheaper and
wrong: the sheet is a mirror, so a row that left the database has to leave the
sheet with it. Two calls per sync, both idempotent, so a failed run is fixed by
running it again.

Credentials, either shape:

- a service account, as the path to its json file or the json itself, which
  needs `pip install "followups[sheets]"` for the RSA signing the standard
  library cannot do, and
- an OAuth access token, which needs nothing extra.

The service account or token needs edit access to the spreadsheet before the
first sync. Configure `GOOGLE_SHEETS_CREDENTIALS`,
`GOOGLE_SHEETS_SPREADSHEET_ID` and optionally `GOOGLE_SHEETS_TAB`, then:

```bash
followups sheets-sync
```

The pipeline never calls it. It is a separate command so that the daily run
stays offline by default, and the sink refuses to construct at all without
credentials.

## Adding a column

The follow-up tables are migrated, not recreated. `CREATE TABLE IF NOT EXISTS`
does nothing to a database that already exists, so a new column added only to
the `CREATE TABLE` statement reaches new installs and nobody else.

Register it in `ADDED_COLUMNS` in
[`store/schema.py`](../src/followups/store/schema.py) instead. `migrate()`
checks `PRAGMA table_info` and applies what is missing, which makes it safe to
run on every start. Pin the new column in
[`tests/test_migrations.py`](../tests/test_migrations.py), which builds the
pre-upgrade schema explicitly and would otherwise never see the gap: tests that
start from a fresh database pass either way.
