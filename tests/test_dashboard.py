"""The dashboard is the surface a non-technical person actually looks at.

It is also the only place prospect-supplied text is rendered as markup, so the
escaping tests here matter more than the layout ones.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from followups.adapters.mock import HtmlDashboardSink
from followups.domain.models import Category, FollowUpRecord, FollowUpState, Track
from tests.conftest import NOW

PAYLOAD = "<script>alert(1)</script>"


def record(
    follow_up_id: str = "f1",
    state: FollowUpState = FollowUpState.PENDING,
    track: Track = Track.DECK,
    category: Category = Category.INTERESTED,
    **overrides: object,
) -> FollowUpRecord:
    fields = {
        "follow_up_id": follow_up_id,
        "prospect_name": "Ada Lovelace",
        "company": "Analytical Co",
        "role": "CTO",
        "category": category,
        "track": track,
        "state": state,
        "reason": "",
        "asset_url": "https://mock.invalid/deck/m1",
        "asset_title": "Analytical Co: next steps",
        "asset_preview_path": "",
        "reply_text": "This sounds good, tell me more about how it works.",
        "message_text": "Ada, glad it landed. I put this together for you:",
        "confidence": 0.87,
        "created_at": NOW,
    }
    fields.update(overrides)
    return FollowUpRecord(**fields)


def render(records, tmp_path) -> str:
    out = tmp_path / "dashboard.html"
    HtmlDashboardSink(out).sync(records)
    return out.read_text()


# -- what a human came to see ---------------------------------------------


def test_summary_tiles_count_every_headline_state(tmp_path):
    page = render(
        [
            record("f1", state=FollowUpState.PENDING),
            record("f2", state=FollowUpState.PENDING),
            record("f3", state=FollowUpState.SENT),
            record("f4", state=FollowUpState.SKIPPED),
            record("f5", state=FollowUpState.FAILED),
        ],
        tmp_path,
    )
    for label, count in (("Pending", 2), ("Sent", 1), ("Skipped", 1), ("Failed", 1)):
        assert f'data-tile="{label}" data-count="{count}"' in page


def test_tiles_are_present_even_at_zero(tmp_path):
    page = render([record("f1")], tmp_path)
    assert 'data-tile="Failed" data-count="0"' in page


def test_the_reply_text_is_visible_on_the_row(tmp_path):
    page = render([record("f1", reply_text="Honestly this looks too expensive.")], tmp_path)
    assert "Honestly this looks too expensive." in page


def test_the_drafted_message_is_visible_on_the_row(tmp_path):
    page = render([record("f1", message_text="Ada, one page on exactly that:")], tmp_path)
    assert "Ada, one page on exactly that:" in page


def test_every_row_carries_its_track_and_state_for_filtering(tmp_path):
    page = render(
        [record("f1", track=Track.VIDEO, state=FollowUpState.SENT)],
        tmp_path,
    )
    assert 'data-track="VIDEO"' in page
    assert 'data-state="SENT"' in page


def test_a_filter_chip_exists_for_each_track_and_state_in_the_data(tmp_path):
    page = render(
        [
            record("f1", track=Track.DECK, state=FollowUpState.PENDING),
            record("f2", track=Track.VISUAL, state=FollowUpState.SKIPPED),
        ],
        tmp_path,
    )
    assert 'data-filter="track" data-value="DECK"' in page
    assert 'data-filter="track" data-value="VISUAL"' in page
    assert 'data-filter="state" data-value="SKIPPED"' in page
    assert 'data-filter="track" data-value="ALL"' in page
    # A track nothing uses does not earn a chip.
    assert 'data-filter="track" data-value="VIDEO"' not in page


def test_filter_chips_carry_their_counts(tmp_path):
    page = render([record("f1"), record("f2")], tmp_path)
    assert 'data-filter="track" data-value="DECK" data-count="2"' in page


def test_the_asset_preview_is_linked_relative_to_the_dashboard(tmp_path):
    preview = tmp_path / "assets" / "deck-m1.html"
    preview.parent.mkdir(parents=True)
    preview.write_text("<p>deck</p>")
    page = render([record("f1", asset_preview_path=str(preview))], tmp_path)
    assert 'href="assets/deck-m1.html"' in page


def test_a_preview_outside_the_dashboard_folder_still_links(tmp_path):
    elsewhere = tmp_path.parent / "elsewhere.html"
    elsewhere.write_text("<p>deck</p>")
    page = render([record("f1", asset_preview_path=str(elsewhere))], tmp_path)
    assert "elsewhere.html" in page


def test_the_hosted_asset_url_is_linked(tmp_path):
    page = render([record("f1", asset_url="https://mock.invalid/deck/m1")], tmp_path)
    assert 'href="https://mock.invalid/deck/m1"' in page


def test_an_empty_queue_says_so_instead_of_showing_an_empty_table(tmp_path):
    page = render([], tmp_path)
    assert "Nothing in the queue yet" in page


def test_the_skip_reason_is_shown(tmp_path):
    page = render(
        [record("f1", state=FollowUpState.SKIPPED, reason="already sent a DECK")],
        tmp_path,
    )
    assert "already sent a DECK" in page


def test_rows_run_newest_first(tmp_path):
    page = render(
        [
            record("f1", prospect_name="Older", created_at=NOW),
            record("f2", prospect_name="Newer", created_at=NOW + timedelta(hours=1)),
        ],
        tmp_path,
    )
    assert page.index("Newer") < page.index("Older")


# -- safety ----------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    ["prospect_name", "company", "role", "reason", "reply_text", "message_text", "asset_title"],
)
def test_untrusted_text_is_escaped_in_every_field(tmp_path, field):
    page = render([record("f1", **{field: PAYLOAD})], tmp_path)
    assert PAYLOAD not in page
    assert "&lt;script&gt;" in page


def test_the_page_opens_exactly_one_script_of_its_own(tmp_path):
    page = render([record("f1", reply_text=PAYLOAD, company=PAYLOAD)], tmp_path)
    assert page.count("<script") == 1


def test_a_non_http_asset_url_is_not_turned_into_a_link(tmp_path):
    page = render([record("f1", asset_url="javascript:alert(1)")], tmp_path)
    assert "javascript:alert(1)" not in page


def test_a_quote_in_prospect_text_cannot_break_out_of_an_attribute(tmp_path):
    page = render([record("f1", company='" onmouseover="alert(1)')], tmp_path)
    assert 'onmouseover="alert(1)' not in page


# -- self-contained and theme aware ---------------------------------------


def test_the_page_pulls_nothing_from_a_cdn(tmp_path):
    page = render([record("f1")], tmp_path)
    assert "<script src" not in page
    assert "<link" not in page
    assert "@import" not in page
    assert "cdn" not in page.lower()


def test_the_page_styles_itself_for_both_colour_schemes(tmp_path):
    page = render([record("f1")], tmp_path)
    assert "prefers-color-scheme: dark" in page
    assert "<style" in page


def test_the_same_records_render_the_same_page(tmp_path):
    first = render([record("f1"), record("f2")], tmp_path)
    second = render([record("f1"), record("f2")], tmp_path)
    assert first == second
