from __future__ import annotations

import ast
from pathlib import Path

DOMAIN = Path(__file__).resolve().parents[1] / "src" / "followups" / "domain"
OUTWARD = ("followups.adapters", "followups.store", "followups.pipeline", "followups.cli")


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def test_domain_does_not_import_outward():
    offenders = [
        (p.name, m)
        for p in DOMAIN.glob("*.py")
        for m in _imported_modules(p)
        if m.startswith(OUTWARD)
    ]
    assert offenders == []
