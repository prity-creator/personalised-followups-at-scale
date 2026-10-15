"""The Google Sheets sink.

Every test here runs offline. The request-shaping tests drive the adapter
through the shared FakeHttpClient, so what the sink would put on the wire is
checked without a wire. The one test that does talk to Google skips unless
both credentials and a spreadsheet id are in the environment, which keeps a
fresh clone green and free.
"""

from __future__ import annotations

import json
import os

import pytest

from followups.adapters.base import MissingCredentials
from followups.adapters.sheets import SheetsSink
from followups.domain.models import Category, FollowUpRecord, FollowUpState, Track
from tests.conftest import NOW
from tests.fakes import FakeHttpClient, ok

TOKEN = "test-access-token"
SHEET_ID = "test-spreadsheet-id"


def record(
    follow_up_id: str = "f1",
    state: FollowUpState = FollowUpState.PENDING,
    **overrides: object,
) -> FollowUpRecord:
    fields = {
        "follow_up_id": follow_up_id,
        "prospect_name": "Ada Lovelace",
        "company": "Analytical Co",
        "role": "CTO",
        "category": Category.INTERESTED,
        "track": Track.DECK,
        "state": state,
        "reason": "",
        "asset_url": "https://mock.invalid/deck/m1",
        "asset_title": "Analytical Co: next steps",
        "asset_preview_path": "/tmp/assets/deck-m1.html",
        "reply_text": "This sounds good, tell me more.",
        "message_text": "Ada, glad it landed.",
        "confidence": 0.87,
        "created_at": NOW,
    }
    fields.update(overrides)
    return FollowUpRecord(**fields)


@pytest.fixture()
def http() -> FakeHttpClient:
    # One response per call a sync makes: clear, then write.
    return FakeHttpClient(responses=[ok({}), ok({})])


@pytest.fixture()
def sink(http) -> SheetsSink:
    return SheetsSink(TOKEN, http=http, spreadsheet_id=SHEET_ID)


def written(http: FakeHttpClient) -> list[list]:
    return http.calls[-1].json_body["values"]


# -- the credential guard --------------------------------------------------


def test_it_refuses_to_construct_without_credentials():
    with pytest.raises(MissingCredentials, match="GOOGLE_SHEETS_CREDENTIALS"):
        SheetsSink("", spreadsheet_id=SHEET_ID)


def test_it_refuses_to_construct_without_a_spreadsheet():
    with pytest.raises(MissingCredentials, match="GOOGLE_SHEETS_SPREADSHEET_ID"):
        SheetsSink(TOKEN, spreadsheet_id="")


def test_from_env_reads_every_variable_it_needs(monkeypatch, http):
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS", TOKEN)
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", SHEET_ID)
    monkeypatch.setenv("GOOGLE_SHEETS_TAB", "Queue")
    sink = SheetsSink.from_env(http=http)
    assert sink.spreadsheet_id == SHEET_ID
    assert sink.tab == "Queue"


def test_from_env_defaults_the_tab(monkeypatch, http):
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS", TOKEN)
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", SHEET_ID)
    monkeypatch.delenv("GOOGLE_SHEETS_TAB", raising=False)
    assert SheetsSink.from_env(http=http).tab == "Follow-ups"


def test_from_env_names_the_missing_spreadsheet_variable(monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS", TOKEN)
    monkeypatch.delenv("GOOGLE_SHEETS_SPREADSHEET_ID", raising=False)
    with pytest.raises(MissingCredentials, match="GOOGLE_SHEETS_SPREADSHEET_ID"):
        SheetsSink.from_env()


# -- what lands in the sheet ----------------------------------------------


def test_the_first_row_is_the_header(sink, http):
    sink.sync([record()])
    assert written(http)[0] == list(SheetsSink.HEADER)


def test_one_row_per_record_in_order(sink, http):
    sink.sync([record("f1"), record("f2"), record("f3")])
    values = written(http)
    assert len(values) == 4
    assert [row[0] for row in values[1:]] == ["f1", "f2", "f3"]


def test_the_row_carries_the_reply_and_the_asset(sink, http):
    sink.sync([record()])
    row = written(http)[1]
    assert "This sounds good, tell me more." in row
    assert "https://mock.invalid/deck/m1" in row


def test_the_row_carries_the_state_the_track_and_the_category(sink, http):
    sink.sync([record(state=FollowUpState.SKIPPED)])
    row = written(http)[1]
    assert "SKIPPED" in row
    assert "DECK" in row
    assert "INTERESTED" in row


def test_the_row_has_one_cell_per_header_column(sink, http):
    sink.sync([record()])
    assert len(written(http)[1]) == len(SheetsSink.HEADER)


def test_every_cell_is_json_serialisable(sink, http):
    sink.sync([record()])
    json.dumps(http.calls[-1].json_body)


def test_an_empty_queue_still_writes_the_header(sink, http):
    sink.sync([])
    assert written(http) == [list(SheetsSink.HEADER)]


# -- how it talks to the API ----------------------------------------------


def test_it_clears_the_sheet_before_writing_it(sink, http):
    """The sheet mirrors the database, so a removed row must not linger."""
    sink.sync([record()])
    assert [call.method for call in http.calls] == ["POST", "PUT"]
    assert http.calls[0].url.endswith(":clear")


def test_it_writes_to_the_values_endpoint_of_the_configured_spreadsheet(sink, http):
    sink.sync([record()])
    url = http.calls[-1].url
    assert url.startswith(f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/")
    assert "valueInputOption=RAW" in url


def test_it_sends_the_bearer_token_with_every_call(sink, http):
    sink.sync([record()])
    assert all(call.headers["Authorization"] == f"Bearer {TOKEN}" for call in http.calls)


def test_a_tab_name_with_a_space_is_quoted_in_the_range(http):
    sink = SheetsSink(TOKEN, http=http, spreadsheet_id=SHEET_ID, tab="Follow ups")
    sink.sync([record()])
    assert "%27Follow%20ups%27%21A%3AZ" in http.calls[-1].url


def test_a_bearer_credential_is_used_as_is(sink):
    assert sink.access_token() == TOKEN


def test_sync_returns_nothing(sink):
    assert sink.sync([record()]) is None


def test_fetch_rows_reads_the_tab_back(http):
    http.responses = [ok({"values": [["Follow-up"], ["f1"]]})]
    sink = SheetsSink(TOKEN, http=http, spreadsheet_id=SHEET_ID)
    assert sink.fetch_rows() == [["Follow-up"], ["f1"]]
    assert http.calls[0].method == "GET"


def test_fetch_rows_on_an_empty_tab_is_an_empty_list(http):
    http.responses = [ok({})]
    assert SheetsSink(TOKEN, http=http, spreadsheet_id=SHEET_ID).fetch_rows() == []


# -- the one test that would touch Google ---------------------------------


@pytest.mark.skipif(
    not (
        os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
        and os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")
    ),
    reason="live Google Sheets credentials are not configured",
)
def test_live_sync_round_trips_through_google_sheets():
    """Overwrites the configured tab, which is a mirror by definition."""
    sink = SheetsSink.from_env()
    sink.sync([record("live-1")])
    rows = sink.fetch_rows()
    assert rows[0] == list(SheetsSink.HEADER)
    assert rows[1][0] == "live-1"
