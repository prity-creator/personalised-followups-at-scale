"""Google Sheets: the CRM-shaped surface for people who want to look at rows.

SQLite stays the source of truth. This is a mirror, which is why the port is
one-way. Swapping it for a HubSpot or Airtable sink means implementing the same
sync method against that vendor and changing one line in the registry.

This is the one real adapter that is implemented rather than stubbed, because
the Sheets API is free and a spreadsheet is the surface a non-technical
operator asks for first. It still costs nothing to have here: it refuses to
construct without credentials and nothing wires it into the default registry,
so an ordinary run never reaches this module.

Docs: https://developers.google.com/sheets/api/reference/rest
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from followups.adapters.base import MissingCredentials, RealAdapter
from followups.adapters.http import HttpClient
from followups.domain.models import FollowUpRecord

DOCS = "https://developers.google.com/sheets/api/reference/rest"
BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets"
SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DEFAULT_TAB = "Follow-ups"

#: Wide enough for the header below, with room to spare on the right.
RANGE_COLUMNS = "A:Z"


class SheetsError(RuntimeError):
    """The sink cannot do what was asked of it."""


class SheetsSink(RealAdapter):
    """Clear the tab and rewrite every record, so the sheet matches the database.

    Rewriting beats appending: the sheet is a mirror, and a row that left the
    database has to leave the sheet with it. Two calls per sync, both
    idempotent, so a failed run is fixed by running it again.
    """

    ENV_KEY = "GOOGLE_SHEETS_CREDENTIALS"
    SPREADSHEET_ENV_KEY = "GOOGLE_SHEETS_SPREADSHEET_ID"
    TAB_ENV_KEY = "GOOGLE_SHEETS_TAB"
    EXTRA_ENV = {
        SPREADSHEET_ENV_KEY: "spreadsheet_id",
        TAB_ENV_KEY: "tab",
    }

    HEADER = (
        "Follow-up",
        "Created",
        "Prospect",
        "Role",
        "Company",
        "Reply",
        "Category",
        "Confidence",
        "Track",
        "State",
        "Reason",
        "Drafted message",
        "Asset",
        "Asset url",
    )

    def __init__(
        self,
        api_key: str,
        http: HttpClient | None = None,
        spreadsheet_id: str = "",
        tab: str = DEFAULT_TAB,
        **options: Any,
    ) -> None:
        super().__init__(api_key, http=http, **options)
        if not spreadsheet_id:
            raise MissingCredentials(
                f"{self.SPREADSHEET_ENV_KEY} is not set. The sheets sink needs a "
                f"spreadsheet to mirror into, and the service account or token "
                f"must already have edit access to it."
            )
        self.spreadsheet_id = spreadsheet_id
        self.tab = tab or DEFAULT_TAB

    # -- the port ----------------------------------------------------------

    def sync(self, records: list[FollowUpRecord]) -> None:
        values = [list(self.HEADER)] + [self.row(record) for record in records]
        headers = self._auth_headers()
        self.http.request("POST", self._url(":clear"), headers=headers, json_body={})
        self.http.request(
            "PUT",
            self._url("", valueInputOption="RAW"),
            headers=headers,
            json_body={"values": values},
        )

    # -- reading back ------------------------------------------------------

    def fetch_rows(self) -> list[list[str]]:
        """Read the tab back. Not part of the port, used to verify a sync."""
        response = self.http.request("GET", self._url(""), headers=self._auth_headers())
        return response.json().get("values", [])

    # -- rows --------------------------------------------------------------

    @classmethod
    def row(cls, record: FollowUpRecord) -> list[Any]:
        """One record as one flat row, in HEADER order, JSON-safe throughout."""
        return [
            record.follow_up_id,
            record.created_at.isoformat(timespec="seconds"),
            record.prospect_name,
            record.role,
            record.company,
            record.reply_text,
            record.category.value,
            round(record.confidence, 2),
            record.track.value,
            record.state.value,
            record.reason,
            record.message_text,
            record.asset_title,
            record.asset_url,
        ]

    # -- auth --------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token()}"}

    def access_token(self) -> str:
        """Turn the configured credential into a bearer token.

        Two shapes are accepted. A service account, given as the path to its
        json file or as the json itself, is exchanged for a short lived token.
        An OAuth access token is used as it stands, which is the path that
        needs nothing beyond the standard library.
        """
        info = self._service_account_info()
        if info is None:
            return self.api_key
        return _mint_service_account_token(info)

    def _service_account_info(self) -> dict[str, Any] | None:
        raw = self.api_key.strip()
        if raw.startswith("{"):
            return json.loads(raw)
        path = Path(raw)
        if path.suffix == ".json" and path.is_file():
            return json.loads(path.read_text())
        return None

    # -- urls --------------------------------------------------------------

    def _url(self, suffix: str, **params: str) -> str:
        # A1 notation with a quoted tab name, so a space or an apostrophe in
        # the tab name cannot change which range is written.
        a1 = "'" + self.tab.replace("'", "''") + f"'!{RANGE_COLUMNS}"
        url = (
            f"{BASE_URL}/{quote(self.spreadsheet_id, safe='')}"
            f"/values/{quote(a1, safe='')}{suffix}"
        )
        if params:
            url += "?" + "&".join(f"{k}={quote(v, safe='')}" for k, v in params.items())
        return url


def _mint_service_account_token(info: dict[str, Any]) -> str:
    """Exchange a service account for an access token, via google-auth.

    Signing the assertion needs RSA, which the standard library does not do,
    so this one path has an optional dependency. Install it with
    `pip install "followups[sheets]"`. Nothing imports it until a service
    account is actually configured, so the default install stays lean.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise SheetsError(
            "A service account credential needs google-auth. Install it with "
            'pip install "followups[sheets]", or set GOOGLE_SHEETS_CREDENTIALS '
            f"to an OAuth access token instead. See {DOCS}."
        ) from exc

    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=[SCOPE]
    )
    credentials.refresh(Request())
    return credentials.token
