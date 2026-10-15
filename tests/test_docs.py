from __future__ import annotations

import re
from pathlib import Path

import pytest

from followups.adapters.registry import ALL_REAL_ADAPTERS

ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"

# Shapes of real credentials for the providers this project talks to.
SECRET_SHAPES = re.compile(r"(sk-ant-|sk-|gho_|ghp_|AIza)[A-Za-z0-9_\-]{12,}")


@pytest.mark.parametrize("cls", ALL_REAL_ADAPTERS, ids=lambda c: c.__name__)
def test_env_example_documents_every_adapter_key(cls):
    assert cls.ENV_KEY in ENV_EXAMPLE.read_text()


def test_env_example_holds_no_real_looking_credential():
    assert SECRET_SHAPES.search(ENV_EXAMPLE.read_text()) is None


def test_gitignore_excludes_the_real_env_file():
    assert ".env" in (ROOT / ".gitignore").read_text().splitlines()


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "docs/architecture.md",
        "docs/mindmap.md",
        "docs/adding-a-track.md",
        "docs/presentation-layer.md",
    ],
)
def test_documentation_exists(path):
    assert (ROOT / path).read_text().strip()


def test_daily_workflow_cannot_fire_unattended_in_a_fork():
    workflow = (ROOT / ".github/workflows/daily.yml").read_text()
    assert "workflow_dispatch" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow


def test_readme_states_the_zero_cost_claim():
    readme = (ROOT / "README.md").read_text().lower()
    assert "no api key" in readme or "without any api key" in readme
