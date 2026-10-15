"""Persistence for prospects, replies, classifications and follow-ups."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime

from followups.domain.cadence import ProspectHistory
from followups.domain.models import (
    Asset,
    Category,
    Classification,
    FollowUp,
    FollowUpRecord,
    FollowUpState,
    Prospect,
    Reply,
    Track,
)


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class Repository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    # -- prospects ---------------------------------------------------------

    def upsert_prospect(self, prospect: Prospect, now: datetime | None = None) -> None:
        self.conn.execute(
            """INSERT INTO prospects (id, name, company, role, linkedin_url, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, company=excluded.company,
                 role=excluded.role, linkedin_url=excluded.linkedin_url""",
            (
                prospect.id,
                prospect.name,
                prospect.company,
                prospect.role,
                prospect.linkedin_url,
                (now or datetime.now().astimezone()).isoformat(),
            ),
        )
        self.conn.commit()

    def get_prospect(self, prospect_id: str) -> Prospect | None:
        row = self.conn.execute(
            "SELECT * FROM prospects WHERE id = ?", (prospect_id,)
        ).fetchone()
        if row is None:
            return None
        return Prospect(
            id=row["id"],
            name=row["name"],
            company=row["company"],
            role=row["role"],
            linkedin_url=row["linkedin_url"],
        )

    # -- replies -----------------------------------------------------------

    def upsert_reply(self, reply: Reply, now: datetime | None = None) -> None:
        """Insert a reply, ignoring one already seen.

        The provider's message id is the primary key, so this is the single
        point where duplicate ingest is prevented.
        """
        self.conn.execute(
            """INSERT INTO replies
               (id, prospect_id, text, received_at, ingested_at,
                conversation_id, account_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO NOTHING""",
            (
                reply.id,
                reply.prospect_id,
                reply.text,
                reply.received_at.isoformat(),
                (now or datetime.now().astimezone()).isoformat(),
                reply.conversation_id,
                reply.account_id,
            ),
        )
        self.conn.commit()

    def unclassified_replies(self) -> list[Reply]:
        rows = self.conn.execute(
            """SELECT r.* FROM replies r
               LEFT JOIN classifications c ON c.reply_id = r.id
               WHERE c.reply_id IS NULL
               ORDER BY r.received_at"""
        ).fetchall()
        return [self._to_reply(r) for r in rows]

    @staticmethod
    def _to_reply(row: sqlite3.Row) -> Reply:
        return Reply(
            id=row["id"],
            prospect_id=row["prospect_id"],
            text=row["text"],
            received_at=datetime.fromisoformat(row["received_at"]),
            conversation_id=row["conversation_id"] or "",
            account_id=row["account_id"],
        )

    def get_reply(self, reply_id: str) -> Reply | None:
        row = self.conn.execute("SELECT * FROM replies WHERE id = ?", (reply_id,)).fetchone()
        return self._to_reply(row) if row else None

    # -- classifications ---------------------------------------------------

    def save_classification(self, reply_id: str, classification: Classification) -> None:
        self.conn.execute(
            """INSERT INTO classifications (reply_id, category, confidence, signals_json)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(reply_id) DO UPDATE SET
                 category=excluded.category, confidence=excluded.confidence,
                 signals_json=excluded.signals_json""",
            (
                reply_id,
                classification.category.value,
                classification.confidence,
                json.dumps(list(classification.signals)),
            ),
        )
        self.conn.commit()

    def get_classification(self, reply_id: str) -> Classification | None:
        row = self.conn.execute(
            "SELECT * FROM classifications WHERE reply_id = ?", (reply_id,)
        ).fetchone()
        if row is None:
            return None
        return Classification(
            category=Category(row["category"]),
            confidence=row["confidence"],
            signals=tuple(json.loads(row["signals_json"])),
        )

    # -- history -----------------------------------------------------------

    def history_for(self, prospect_id: str) -> ProspectHistory:
        sent = self.conn.execute(
            """SELECT track, sent_at FROM follow_ups
               WHERE prospect_id = ? AND state = ?""",
            (prospect_id, FollowUpState.SENT.value),
        ).fetchall()
        open_count = self.conn.execute(
            """SELECT COUNT(*) AS n FROM follow_ups
               WHERE prospect_id = ? AND state IN (?, ?)""",
            (prospect_id, FollowUpState.PENDING.value, FollowUpState.APPROVED.value),
        ).fetchone()["n"]
        last_reply = self.conn.execute(
            "SELECT MAX(received_at) AS t FROM replies WHERE prospect_id = ?",
            (prospect_id,),
        ).fetchone()["t"]

        sent_times = [_dt(r["sent_at"]) for r in sent if r["sent_at"]]
        return ProspectHistory(
            tracks_sent=frozenset(Track(r["track"]) for r in sent),
            last_sent_at=max(sent_times) if sent_times else None,
            touches=len(sent),
            last_reply_at=_dt(last_reply),
            has_open_queue=open_count > 0,
        )

    # -- follow-ups --------------------------------------------------------

    def queue(self, follow_up: FollowUp, now: datetime) -> None:
        asset = follow_up.asset
        self.conn.execute(
            """INSERT INTO follow_ups
               (id, prospect_id, reply_id, track, asset_url, asset_title,
                asset_preview, message_text, state, reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                follow_up.id,
                follow_up.prospect_id,
                follow_up.reply_id,
                follow_up.track.value,
                asset.url if asset else "",
                asset.title if asset else "",
                asset.preview_path if asset else "",
                follow_up.message_text,
                follow_up.state.value,
                follow_up.reason,
                now.isoformat(),
            ),
        )
        self.conn.commit()

    def _by_state(self, state: FollowUpState) -> list[FollowUp]:
        rows = self.conn.execute(
            "SELECT * FROM follow_ups WHERE state = ? ORDER BY created_at, id",
            (state.value,),
        ).fetchall()
        return [self._to_follow_up(r) for r in rows]

    @staticmethod
    def _to_follow_up(row: sqlite3.Row) -> FollowUp:
        track = Track(row["track"])
        asset = (
            Asset(
                track=track,
                url=row["asset_url"],
                title=row["asset_title"],
                preview_path=row["asset_preview"],
            )
            if row["asset_url"]
            else None
        )
        return FollowUp(
            id=row["id"],
            prospect_id=row["prospect_id"],
            reply_id=row["reply_id"],
            track=track,
            asset=asset,
            message_text=row["message_text"],
            state=FollowUpState(row["state"]),
            reason=row["reason"],
        )

    def pending(self) -> list[FollowUp]:
        return self._by_state(FollowUpState.PENDING)

    def approved(self) -> list[FollowUp]:
        return self._by_state(FollowUpState.APPROVED)

    def set_state(
        self,
        follow_up_id: str,
        state: FollowUpState,
        reason: str | None = None,
        sent_at: datetime | None = None,
    ) -> None:
        self.conn.execute(
            """UPDATE follow_ups
               SET state = ?,
                   reason = COALESCE(?, reason),
                   decided_at = COALESCE(decided_at, ?),
                   sent_at = COALESCE(?, sent_at)
               WHERE id = ?""",
            (
                state.value,
                reason,
                (sent_at or datetime.now().astimezone()).isoformat(),
                sent_at.isoformat() if sent_at else None,
                follow_up_id,
            ),
        )
        self.conn.commit()

    def all_records(self) -> list[FollowUpRecord]:
        rows = self.conn.execute(
            """SELECT f.*,
                      p.name AS pname, p.company AS pcompany, p.role AS prole,
                      c.category AS category, c.confidence AS confidence,
                      r.text AS reply_text
               FROM follow_ups f
               LEFT JOIN prospects p ON p.id = f.prospect_id
               LEFT JOIN classifications c ON c.reply_id = f.reply_id
               LEFT JOIN replies r ON r.id = f.reply_id
               ORDER BY f.created_at, f.id"""
        ).fetchall()
        return [
            FollowUpRecord(
                follow_up_id=r["id"],
                prospect_name=r["pname"] or r["prospect_id"],
                company=r["pcompany"] or "",
                category=Category(r["category"]) if r["category"] else Category.UNCLEAR,
                track=Track(r["track"]),
                state=FollowUpState(r["state"]),
                reason=r["reason"],
                asset_url=r["asset_url"],
                created_at=datetime.fromisoformat(r["created_at"]),
                role=r["prole"] or "",
                reply_text=r["reply_text"] or "",
                message_text=r["message_text"],
                asset_title=r["asset_title"],
                asset_preview_path=r["asset_preview"],
                confidence=r["confidence"] or 0.0,
            )
            for r in rows
        ]

    # -- runs --------------------------------------------------------------

    def start_run(self, now: datetime) -> str:
        run_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO runs (id, started_at) VALUES (?, ?)", (run_id, now.isoformat())
        )
        self.conn.commit()
        return run_id

    def finish_run(self, run_id: str, counts: dict, now: datetime) -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at = ?, counts_json = ? WHERE id = ?",
            (now.isoformat(), json.dumps(counts), run_id),
        )
        self.conn.commit()

    def last_run_started_at(self) -> datetime | None:
        row = self.conn.execute("SELECT MAX(started_at) AS t FROM runs").fetchone()
        return _dt(row["t"]) if row and row["t"] else None
