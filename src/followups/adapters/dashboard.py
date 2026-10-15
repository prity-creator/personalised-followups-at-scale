"""The dashboard: one self-contained HTML page per run.

This is the presentation half of the CrmSink port, kept out of mock.py because
it is mostly markup. One file, no network, no build step, no CDN: a page that
opens from a file path on any machine and reads the same in a light or a dark
colour scheme.

Everything a prospect wrote reaches this module, so every value interpolated
into markup goes through escape() and every url through _safe_href(). The tests
in tests/test_dashboard.py hold that line.
"""

from __future__ import annotations

from collections import Counter
from html import escape
from pathlib import Path
from urllib.parse import quote

from followups.domain.models import FollowUpRecord, FollowUpState, Track

TITLE = "Follow-up queue"

# The four numbers someone wants before they want any row.
TILES: list[tuple[FollowUpState, str, str]] = [
    (FollowUpState.PENDING, "Pending", "waiting on a human"),
    (FollowUpState.SENT, "Sent", "delivered to the prospect"),
    (FollowUpState.SKIPPED, "Skipped", "held back by the cadence rules"),
    (FollowUpState.FAILED, "Failed", "generator or send error"),
]

TRACK_BLURB = {
    Track.DECK: "slide deck",
    Track.VIDEO: "personalised video",
    Track.VISUAL: "one page visual",
    Track.NONE: "no resource",
}

STATE_ORDER = [
    FollowUpState.PENDING,
    FollowUpState.APPROVED,
    FollowUpState.SENT,
    FollowUpState.REJECTED,
    FollowUpState.SKIPPED,
    FollowUpState.FAILED,
]

TRACK_ORDER = [Track.DECK, Track.VIDEO, Track.VISUAL, Track.NONE]

SAFE_SCHEMES = ("http://", "https://", "file://")

CSS = """
:root {
  color-scheme: light dark;
  --bg: #f7f6f2;
  --surface: #ffffff;
  --surface-2: #f2f1ea;
  --ink: #23231f;
  --muted: #6b6a63;
  --line: #e2e0d6;
  --accent: #2f6690;
  --shadow: 0 1px 2px rgba(31, 30, 26, .06), 0 8px 24px rgba(31, 30, 26, .04);
  --pending: #9a6700; --pending-bg: #fff4d6;
  --approved: #2f6690; --approved-bg: #ddebf5;
  --sent: #246b45; --sent-bg: #d9efe2;
  --rejected: #6b4a7a; --rejected-bg: #efe4f3;
  --skipped: #5f5e58; --skipped-bg: #e8e7df;
  --failed: #9c2f2f; --failed-bg: #fadede;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #15161a;
    --surface: #1d1f24;
    --surface-2: #23262c;
    --ink: #e8e7e1;
    --muted: #9b9a93;
    --line: #30333a;
    --accent: #7fb2d8;
    --shadow: none;
    --pending: #f0c250; --pending-bg: #3a2f10;
    --approved: #8fc0e4; --approved-bg: #16303f;
    --sent: #7ed9a6; --sent-bg: #123a28;
    --rejected: #cfa8dd; --rejected-bg: #2e2135;
    --skipped: #b4b3ab; --skipped-bg: #2a2c31;
    --failed: #f09b9b; --failed-bg: #3a1a1a;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 2.5rem 1.25rem 4rem;
  background: var(--bg);
  color: var(--ink);
  font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1040px; margin: 0 auto; }
header h1 { margin: 0 0 .25rem; font-size: 1.6rem; letter-spacing: -.01em; }
header p { margin: 0; color: var(--muted); font-size: .9rem; }
.tiles {
  display: grid; gap: .75rem; margin: 1.75rem 0 1.5rem;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
}
.tile {
  background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
  padding: .9rem 1rem; box-shadow: var(--shadow);
}
.tile b { display: block; font-size: 2rem; font-weight: 600; line-height: 1.1; }
.tile .label { font-size: .8rem; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; }
.tile .note { color: var(--muted); font-size: .78rem; }
.tile.pending b, .tile.pending .label { color: var(--pending); }
.tile.sent b, .tile.sent .label { color: var(--sent); }
.tile.skipped b, .tile.skipped .label { color: var(--skipped); }
.tile.failed b, .tile.failed .label { color: var(--failed); }
.controls {
  display: flex; flex-wrap: wrap; gap: .75rem 1.5rem; align-items: center;
  padding: .9rem 1rem; margin-bottom: 1rem;
  background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
}
.group { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; }
.group > span { font-size: .72rem; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); margin-right: .2rem; }
.chip {
  font: inherit; font-size: .82rem; cursor: pointer;
  background: var(--surface-2); color: var(--ink);
  border: 1px solid var(--line); border-radius: 999px; padding: .25rem .7rem;
}
.chip:hover { border-color: var(--accent); }
.chip[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--surface); }
.chip .n { opacity: .65; margin-left: .3rem; font-variant-numeric: tabular-nums; }
input[type="search"] {
  font: inherit; font-size: .85rem; flex: 1 1 180px; min-width: 150px;
  padding: .35rem .6rem; border-radius: 8px;
  border: 1px solid var(--line); background: var(--surface-2); color: var(--ink);
}
.count { color: var(--muted); font-size: .82rem; margin: 0 0 .75rem; }
.rows { display: grid; gap: .75rem; }
.row {
  background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
  padding: 1rem 1.1rem; box-shadow: var(--shadow);
}
.row.is-hidden { display: none; }
.row header { display: flex; flex-wrap: wrap; gap: .5rem; align-items: baseline; justify-content: space-between; }
.who { font-weight: 600; }
.who small { font-weight: 400; color: var(--muted); }
.badges { display: flex; flex-wrap: wrap; gap: .35rem; }
.badge {
  font-size: .72rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
  border-radius: 999px; padding: .15rem .55rem; background: var(--surface-2); color: var(--muted);
}
.badge.state-PENDING { background: var(--pending-bg); color: var(--pending); }
.badge.state-APPROVED { background: var(--approved-bg); color: var(--approved); }
.badge.state-SENT { background: var(--sent-bg); color: var(--sent); }
.badge.state-REJECTED { background: var(--rejected-bg); color: var(--rejected); }
.badge.state-SKIPPED { background: var(--skipped-bg); color: var(--skipped); }
.badge.state-FAILED { background: var(--failed-bg); color: var(--failed); }
blockquote {
  margin: .8rem 0 0; padding: .6rem .9rem;
  background: var(--surface-2); border-left: 3px solid var(--line); border-radius: 0 8px 8px 0;
}
blockquote .cap, .draft .cap {
  display: block; font-size: .7rem; text-transform: uppercase; letter-spacing: .07em;
  color: var(--muted); margin-bottom: .2rem;
}
.draft { margin-top: .7rem; }
.draft p { margin: 0; }
.row footer {
  display: flex; flex-wrap: wrap; gap: .4rem 1rem; align-items: center;
  margin-top: .85rem; padding-top: .7rem; border-top: 1px solid var(--line);
  font-size: .82rem; color: var(--muted);
}
.row footer a { color: var(--accent); text-decoration: none; font-weight: 500; }
.row footer a:hover { text-decoration: underline; }
.empty {
  background: var(--surface); border: 1px dashed var(--line); border-radius: 12px;
  padding: 2.5rem 1rem; text-align: center; color: var(--muted);
}
.foot { margin-top: 2rem; color: var(--muted); font-size: .78rem; }
"""

# Filtering is a page concern, not a server concern: no rebuild, no requests,
# and the page still shows every row with scripting switched off.
JS = """
(function () {
  var rows = Array.prototype.slice.call(document.querySelectorAll(".row"));
  var chips = Array.prototype.slice.call(document.querySelectorAll(".chip"));
  var search = document.getElementById("q");
  var count = document.getElementById("count");
  var picked = { track: "ALL", state: "ALL" };

  function apply() {
    var q = (search && search.value || "").toLowerCase().trim();
    var shown = 0;
    rows.forEach(function (row) {
      var ok =
        (picked.track === "ALL" || row.dataset.track === picked.track) &&
        (picked.state === "ALL" || row.dataset.state === picked.state) &&
        (q === "" || row.dataset.search.indexOf(q) !== -1);
      row.classList.toggle("is-hidden", !ok);
      if (ok) { shown++; }
    });
    if (count) {
      count.textContent = "Showing " + shown + " of " + rows.length + " follow-ups";
    }
  }

  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      var kind = chip.dataset.filter;
      picked[kind] = chip.dataset.value;
      chips.forEach(function (other) {
        if (other.dataset.filter === kind) {
          other.setAttribute("aria-pressed", String(other === chip));
        }
      });
      apply();
    });
  });
  if (search) { search.addEventListener("input", apply); }
  apply();
})();
"""


def _safe_href(url: str) -> str:
    """Return an attribute-safe href, or an empty string for anything exotic.

    Asset urls come from our own generators, but a sink that only links schemes
    it recognises cannot be turned into a javascript: link by a bad record.
    """
    if not url.startswith(SAFE_SCHEMES):
        return ""
    return escape(url, quote=True)


def _preview_href(preview_path: str, base_dir: Path | None) -> str:
    """Link the local preview file, relative to the dashboard where possible."""
    if not preview_path:
        return ""
    path = Path(preview_path)
    if base_dir is not None:
        try:
            relative = path.resolve().relative_to(base_dir.resolve())
        except (ValueError, OSError):
            pass
        else:
            return escape(quote(relative.as_posix()), quote=True)
    if path.is_absolute():
        return escape(path.as_uri(), quote=True)
    return escape(quote(path.as_posix()), quote=True)


def _chip(kind: str, value: str, label: str, count: int, pressed: bool) -> str:
    return (
        f'<button class="chip" type="button" data-filter="{kind}" '
        f'data-value="{value}" data-count="{count}" '
        f'aria-pressed="{"true" if pressed else "false"}">'
        f'{escape(label)}<span class="n">{count}</span></button>'
    )


def _chip_group(
    kind: str, label: str, order: list, counts: Counter, total: int
) -> str:
    chips = [_chip(kind, "ALL", "All", total, True)]
    chips += [
        _chip(kind, member.value, member.value.title(), counts[member], False)
        for member in order
        if counts[member]
    ]
    return f'<div class="group"><span>{label}</span>{"".join(chips)}</div>'


def _tiles(counts: Counter) -> str:
    cells = [
        f'<div class="tile {state.value.lower()}" data-tile="{label}" '
        f'data-count="{counts[state]}">'
        f"<b>{counts[state]}</b>"
        f'<div class="label">{label}</div>'
        f'<div class="note">{note}</div></div>'
        for state, label, note in TILES
    ]
    return f'<section class="tiles">{"".join(cells)}</section>'


def _row(record: FollowUpRecord, base_dir: Path | None) -> str:
    name = escape(record.prospect_name or "Unknown prospect")
    company = escape(record.company)
    role = escape(record.role)
    where = ", ".join(part for part in (role, company) if part)

    badges = [
        f'<span class="badge state-{record.state.value}">{record.state.value}</span>',
        f'<span class="badge">{record.track.value}</span>',
        f'<span class="badge">{record.category.value}</span>',
    ]
    if record.confidence:
        badges.append(f'<span class="badge">{record.confidence:.0%} sure</span>')

    parts = [
        '<header>'
        f'<div class="who">{name}'
        + (f" <small>{where}</small>" if where else "")
        + "</div>"
        f'<div class="badges">{"".join(badges)}</div>'
        "</header>"
    ]

    if record.reply_text:
        parts.append(
            '<blockquote><span class="cap">They replied</span>'
            f"{escape(record.reply_text)}</blockquote>"
        )
    if record.message_text:
        parts.append(
            '<div class="draft"><span class="cap">We would send</span>'
            f"<p>{escape(record.message_text)}</p></div>"
        )
    if record.reason:
        parts.append(
            '<div class="draft"><span class="cap">Why not sent</span>'
            f"<p>{escape(record.reason)}</p></div>"
        )

    links = []
    asset_href = _safe_href(record.asset_url)
    if asset_href:
        label = escape(record.asset_title or TRACK_BLURB.get(record.track, "asset"))
        links.append(f'<a href="{asset_href}">{label}</a>')
    preview_href = _preview_href(record.asset_preview_path, base_dir)
    if preview_href:
        links.append(f'<a href="{preview_href}">preview the {TRACK_BLURB.get(record.track, "asset")}</a>')
    links.append(f'<span>{record.created_at.strftime("%d %b %Y, %H:%M")}</span>')
    parts.append(f'<footer>{"".join(links)}</footer>')

    haystack = escape(
        " ".join(
            (
                record.prospect_name,
                record.company,
                record.role,
                record.reply_text,
                record.message_text,
                record.reason,
                record.category.value,
            )
        ).lower(),
        quote=True,
    )
    return (
        f'<article class="row" data-track="{record.track.value}" '
        f'data-state="{record.state.value}" data-search="{haystack}">'
        + "".join(parts)
        + "</article>"
    )


def render(records: list[FollowUpRecord], base_dir: Path | None = None) -> str:
    """Render the whole queue as one standalone page.

    Newest first, because the thing that just happened is the thing someone
    came to look at.
    """
    ordered = sorted(records, key=lambda r: (r.created_at, r.follow_up_id), reverse=True)
    states = Counter(r.state for r in ordered)
    tracks = Counter(r.track for r in ordered)

    if ordered:
        latest = max(r.created_at for r in ordered)
        subtitle = (
            f"{len(ordered)} follow-ups mirrored from SQLite. "
            f"Latest activity {latest.strftime('%d %b %Y, %H:%M')}."
        )
        body = (
            '<section class="controls">'
            + _chip_group("track", "Track", TRACK_ORDER, tracks, len(ordered))
            + _chip_group("state", "State", STATE_ORDER, states, len(ordered))
            + '<input type="search" id="q" placeholder="Search a name, company or reply">'
            + "</section>"
            f'<p class="count" id="count">Showing {len(ordered)} of {len(ordered)} follow-ups</p>'
            f'<div class="rows">{"".join(_row(r, base_dir) for r in ordered)}</div>'
        )
    else:
        subtitle = "Nothing has run yet."
        body = (
            '<div class="empty"><p><strong>Nothing in the queue yet.</strong></p>'
            "<p>Run <code>followups seed</code> then <code>followups run</code>, "
            "and this page fills itself in.</p></div>"
        )

    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{TITLE}</title>"
        f"<style>{CSS}</style></head>"
        '<body><div class="wrap">'
        f"<header><h1>{TITLE}</h1><p>{subtitle}</p></header>"
        + _tiles(states)
        + body
        + '<p class="foot">Generated by followups. SQLite is the source of truth, '
        "this page is a mirror of it.</p>"
        "</div>"
        f"<script>{JS}</script>"
        "</body></html>\n"
    )
