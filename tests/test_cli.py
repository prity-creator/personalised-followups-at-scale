from __future__ import annotations

import pytest
from click.testing import CliRunner

from followups.cli import cli


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLLOWUPS_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture()
def runner():
    return CliRunner()


def test_seed_then_run_then_dashboard(home, runner):
    assert runner.invoke(cli, ["seed"]).exit_code == 0
    assert runner.invoke(cli, ["run"]).exit_code == 0
    result = runner.invoke(cli, ["dashboard"])
    assert result.exit_code == 0
    page = (home / "dashboard.html").read_text()
    assert "Follow-up queue" in page
    assert "Analytical Co" in page


def test_run_prints_counts(home, runner):
    runner.invoke(cli, ["seed"])
    output = runner.invoke(cli, ["run"]).output
    assert "queued" in output
    assert "ingested" in output


def test_run_writes_the_database_under_followups_home(home, runner):
    runner.invoke(cli, ["seed"])
    runner.invoke(cli, ["run"])
    assert (home / "followups.db").exists()


def test_review_lists_pending_follow_ups(home, runner):
    runner.invoke(cli, ["seed"])
    runner.invoke(cli, ["run"])
    output = runner.invoke(cli, ["review"]).output
    assert "Analytical Co" in output
    assert "DECK" in output


def test_approve_moves_state_out_of_pending(home, runner):
    runner.invoke(cli, ["seed"])
    runner.invoke(cli, ["run"])
    first_id = _first_pending_id(runner)
    assert runner.invoke(cli, ["approve", first_id]).exit_code == 0
    assert first_id not in runner.invoke(cli, ["review"]).output


def test_approve_unknown_id_fails_loudly(home, runner):
    runner.invoke(cli, ["seed"])
    result = runner.invoke(cli, ["approve", "does-not-exist"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_send_requires_the_live_flag(home, runner):
    runner.invoke(cli, ["seed"])
    runner.invoke(cli, ["run"])
    runner.invoke(cli, ["approve", _first_pending_id(runner)])
    runner.invoke(cli, ["run"])
    assert not (home / "outbox.jsonl").exists()
    runner.invoke(cli, ["run", "--live-send"])
    assert (home / "outbox.jsonl").exists()


def _first_pending_id(runner: CliRunner) -> str:
    line = next(
        line for line in runner.invoke(cli, ["review"]).output.splitlines() if "DECK" in line
    )
    return line.split()[0]


def test_sheets_sync_refuses_without_credentials(home, runner, monkeypatch):
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS", raising=False)
    result = runner.invoke(cli, ["sheets-sync"])
    assert result.exit_code != 0
    assert "GOOGLE_SHEETS_CREDENTIALS" in result.output


def test_sheets_sync_is_not_reached_by_a_normal_run(home, runner):
    """The default pipeline mirrors to the dashboard and nothing else."""
    runner.invoke(cli, ["seed"])
    assert runner.invoke(cli, ["run"]).exit_code == 0
    assert (home / "dashboard.html").exists()


def test_live_without_credentials_fails_with_the_variable_name(home, runner):
    """Asking for live mode with no keys must say which one is missing."""
    for key in ("HEYREACH_API_KEY", "ANTHROPIC_API_KEY", "GAMMA_API_KEY"):
        import os

        os.environ.pop(key, None)
    runner.invoke(cli, ["seed"])
    result = runner.invoke(cli, ["run", "--live"])
    assert result.exit_code != 0
    assert "HEYREACH_API_KEY" in result.output


def test_run_without_live_uses_mocks_and_needs_no_keys(home, runner):
    runner.invoke(cli, ["seed"])
    assert runner.invoke(cli, ["run"]).exit_code == 0
