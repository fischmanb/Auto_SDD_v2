"""Shared fixtures for Auto-SDD V2 tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project directory with package.json and specs."""
    (tmp_path / ".specs").mkdir()
    (tmp_path / ".specs" / "roadmap.md").write_text(
        "| ID | Name | Domain | Deps | Complexity | Notes | Status |\n"
        "|----|------|--------|------|------------|-------|--------|\n"
        "| 1 | Auth | core | - | M | - | ✅ |\n"
        "| 2 | Dashboard | ui | Auth | L | - | ⬜ |\n"
    )
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"build": "tsc", "test": "jest", "dev": "next dev"},
        "devDependencies": {"typescript": "5.0", "eslint": "8.0"},
        "dependencies": {"react": "18.0"},
    }))
    (tmp_path / "tsconfig.json").write_text("{}")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export const x = 1;\n")
    return tmp_path
