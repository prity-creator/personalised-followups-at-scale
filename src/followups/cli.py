"""Command line entry point.

Everything the system does is reachable from here, and every command resolves
its working data from FOLLOWUPS_HOME so a run never writes into the repository
by surprise.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import click

from followups.adapters.mock import FixtureProspects
from followups.adapters.registry import FIXTURES_DIR, default_registry
from followups.domain.models import FollowUpState
from followups.domain.routing import load_routing
from followups.pipeline.daily import run as run_pipeline
from followups.store.repository import Repository
from followups.store.schema import migrate


def _home() -> Path:
    home = Path(os.environ.get("FOLLOWUPS_HOME", Path.cwd()))
    home.mkdir(parents=True, exist_ok=True)
    return home


def _repository(home: Path) -> Repository:
    conn = sqlite3.connect(home / "followups.db")
    migrate(conn)
    return Repository(conn)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@click.group()
def cli() -> None:
    """Follow-ups through personalised resources at scale."""


@cli.command()
def seed() -> None:
    """Load the fixture prospects into a fresh database."""
    home = _home()
    repo = _repository(home)
    prospects = FixtureProspects(FIXTURES_DIR / "prospects.json").all()
    for prospect in prospects:
        repo.upsert_prospect(prospect, _now())
    click.echo(f"seeded {len(prospects)} prospects into {home / 'followups.db'}")


@cli.command()
@click.option(
    "--live-send",
    is_flag=True,
    help="Actually hand approved follow-ups to the sender. Off by default.",
)
def run(live_send: bool) -> None:
    """Run one pipeline pass: ingest, classify, route, generate, queue."""
    home = _home()
    repo = _repository(home)
    counts = run_pipeline(
        repo,
        default_registry(home),
        load_routing(),
        now=_now(),
        live_send=live_send,
    )
    for name, value in counts.as_dict().items():
        click.echo(f"{name:>10}: {value}")


@cli.command()
def review() -> None:
    """List the follow-ups waiting for a decision."""
    repo = _repository(_home())
    pending = repo.pending()
    if not pending:
        click.echo("nothing pending")
        return
    records = {r.follow_up_id: r for r in repo.all_records()}
    for follow_up in pending:
        record = records.get(follow_up.id)
        company = record.company if record else ""
        asset = follow_up.asset.url if follow_up.asset else ""
        click.echo(f"{follow_up.id}  {follow_up.track.value:<6}  {company:<20}  {asset}")
    click.echo(f"\n{len(pending)} pending. Approve with: followups approve <id>")


@cli.command()
@click.argument("follow_up_id")
def approve(follow_up_id: str) -> None:
    """Approve one follow-up so the next run may send it."""
    repo = _repository(_home())
    if all(f.id != follow_up_id for f in repo.pending()):
        raise click.ClickException(f"pending follow-up {follow_up_id} not found")
    repo.set_state(follow_up_id, FollowUpState.APPROVED)
    click.echo(f"approved {follow_up_id}")


@cli.command()
@click.argument("follow_up_id")
def reject(follow_up_id: str) -> None:
    """Reject one follow-up so it is never sent."""
    repo = _repository(_home())
    if all(f.id != follow_up_id for f in repo.pending()):
        raise click.ClickException(f"pending follow-up {follow_up_id} not found")
    repo.set_state(follow_up_id, FollowUpState.REJECTED, reason="rejected by operator")
    click.echo(f"rejected {follow_up_id}")


@cli.command()
def dashboard() -> None:
    """Regenerate the local dashboard from the database."""
    home = _home()
    repo = _repository(home)
    sink = default_registry(home).crm_sink
    sink.sync(repo.all_records())
    click.echo(f"wrote {home / 'dashboard.html'}")


if __name__ == "__main__":
    cli()
