"""Google Sheets: the CRM-shaped surface for people who want to look at rows.

SQLite stays the source of truth. This is a mirror, which is why the port is
one-way. Swapping it for a HubSpot or Airtable sink means implementing the same
sync method against that vendor and changing one line in the registry.
"""

from __future__ import annotations

from followups.adapters.base import RealAdapter
from followups.domain.models import FollowUpRecord

DOCS = "https://developers.google.com/sheets/api/reference/rest"


class SheetsSink(RealAdapter):
    """Clear the sheet and append every record, so the sheet matches the database."""

    ENV_KEY = "GOOGLE_SHEETS_CREDENTIALS"
    SPREADSHEET_ENV_KEY = "GOOGLE_SHEETS_SPREADSHEET_ID"

    def sync(self, records: list[FollowUpRecord]) -> None:
        raise self._not_implemented("POST /v4/spreadsheets/{id}/values:append", DOCS)
