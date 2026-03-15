"""Tests for codebase_summary.py — file tree, cache, learnings."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from auto_sdd.lib.codebase_summary import (
    _generate_file_tree, _FILE_TREE_CAP,
    _get_tree_hash, _read_cache, _write_cache,
    _read_recent_learnings,
    generate_codebase_summary,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Project with a few files."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')")
    (tmp_path / "src" / "utils.py").write_text("def f(): pass")
    (tmp_path / "README.md").write_text("# readme")
    return tmp_path


# ── File tree ────────────────────────────────────────────────────────────────


class TestGenerateFileTree:

    def test_lists_files(self, project: Path) -> None:
        tree = _generate_file_tree(project)
        assert "src/main.py" in tree
        assert "src/utils.py" in tree
        assert "README.md" in tree

    def test_excludes_node_modules(self, tmp_path: Path) -> None:
        (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
        (tmp_path / "node_modules" / "pkg" / "index.js").write_text("")
        (tmp_path / "app.js").write_text("")
        tree = _generate_file_tree(tmp_path)
        assert "app.js" in tree
        assert "node_modules" not in tree

    def test_excludes_git(self, tmp_path: Path) -> None:
        (tmp_path / ".git" / "objects").mkdir(parents=True)
        (tmp_path / ".git" / "objects" / "abc").write_text("")
        (tmp_path / "src.py").write_text("")
        tree = _generate_file_tree(tmp_path)
        assert "src.py" in tree
        assert ".git" not in tree

    def test_excludes_pycache(self, tmp_path: Path) -> None:
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "mod.pyc").write_text("")
        (tmp_path / "mod.py").write_text("")
        tree = _generate_file_tree(tmp_path)
        assert "mod.py" in tree
        assert "__pycache__" not in tree

    def test_excludes_sdd_dirs(self, tmp_path: Path) -> None:
        for d in [".auto-sdd-cache", ".specs", ".sdd-state"]:
            (tmp_path / d).mkdir()
            (tmp_path / d / "data.md").write_text("")
        (tmp_path / "app.py").write_text("")
        tree = _generate_file_tree(tmp_path)
        assert "app.py" in tree
        assert ".auto-sdd-cache" not in tree
        assert ".specs" not in tree
        assert ".sdd-state" not in tree

    def test_truncates_at_cap(self, tmp_path: Path) -> None:
        for i in range(_FILE_TREE_CAP + 10):
            (tmp_path / f"file_{i:04d}.txt").write_text("")
        tree = _generate_file_tree(tmp_path)
        assert f"truncated at {_FILE_TREE_CAP}" in tree

    def test_empty_dir(self, tmp_path: Path) -> None:
        assert _generate_file_tree(tmp_path) == ""


# ── Cache layer ──────────────────────────────────────────────────────────────


class TestCacheLayer:

    def test_read_miss(self, tmp_path: Path) -> None:
        assert _read_cache(tmp_path, "abc123") is None

    def test_write_then_read(self, tmp_path: Path) -> None:
        _write_cache(tmp_path, "abc123", "summary content")
        assert _read_cache(tmp_path, "abc123") == "summary content"

    def test_different_hash_miss(self, tmp_path: Path) -> None:
        _write_cache(tmp_path, "abc123", "old")
        assert _read_cache(tmp_path, "def456") is None

    def test_gitignore_created(self, tmp_path: Path) -> None:
        _write_cache(tmp_path, "abc", "x")
        gi = tmp_path / ".auto-sdd-cache" / ".gitignore"
        assert gi.exists()
        assert gi.read_text() == "*\n"


# ── Learnings ────────────────────────────────────────────────────────────────


class TestReadLearnings:

    def test_no_learnings_dir(self, tmp_path: Path) -> None:
        assert _read_recent_learnings(tmp_path) == ""

    def test_empty_learnings_dir(self, tmp_path: Path) -> None:
        (tmp_path / ".specs" / "learnings").mkdir(parents=True)
        assert _read_recent_learnings(tmp_path) == ""

    def test_reads_markdown_files(self, tmp_path: Path) -> None:
        ld = tmp_path / ".specs" / "learnings"
        ld.mkdir(parents=True)
        (ld / "general.md").write_text("Use tokens for colors.\n")
        result = _read_recent_learnings(tmp_path)
        assert "Recent Learnings" in result
        assert "general.md" in result
        assert "Use tokens for colors" in result

    def test_skips_empty_files(self, tmp_path: Path) -> None:
        ld = tmp_path / ".specs" / "learnings"
        ld.mkdir(parents=True)
        (ld / "empty.md").write_text("")
        (ld / "real.md").write_text("content\n")
        result = _read_recent_learnings(tmp_path)
        assert "empty.md" not in result
        assert "real.md" in result


# ── Integration (generate_codebase_summary) ──────────────────────────────────


class TestGenerateCodebaseSummary:

    def test_not_a_dir(self, tmp_path: Path) -> None:
        fake = tmp_path / "nonexistent"
        assert generate_codebase_summary(fake) == ""

    def test_empty_project(self, tmp_path: Path) -> None:
        """Empty dir returns empty string (no files to summarize)."""
        assert generate_codebase_summary(tmp_path) == ""

    def test_no_config_skips_agent(self, project: Path) -> None:
        """Without config, agent is not called. Returns empty (no cache)."""
        result = generate_codebase_summary(project, config=None)
        # No cache, no agent — empty string
        assert result == ""

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_cache_hit_skips_agent(
        self, mock_hash: MagicMock, mock_agent: MagicMock, project: Path,
    ) -> None:
        mock_hash.return_value = "abc123"
        _write_cache(project, "abc123", "cached summary")
        result = generate_codebase_summary(project, config=object())
        assert "cached summary" in result
        mock_agent.assert_not_called()

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_cache_miss_calls_agent(
        self, mock_hash: MagicMock, mock_agent: MagicMock, project: Path,
    ) -> None:
        mock_hash.return_value = "def456"
        mock_agent.return_value = "agent summary"
        result = generate_codebase_summary(project, config=object())
        assert "agent summary" in result
        mock_agent.assert_called_once()

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_caches_after_agent_call(
        self, mock_hash: MagicMock, mock_agent: MagicMock, project: Path,
    ) -> None:
        mock_hash.return_value = "newhash"
        mock_agent.return_value = "fresh summary"
        generate_codebase_summary(project, config=object())
        cached = _read_cache(project, "newhash")
        assert cached == "fresh summary"

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_agent_failure_returns_empty(
        self, mock_hash: MagicMock, mock_agent: MagicMock, project: Path,
    ) -> None:
        mock_hash.return_value = "abc"
        mock_agent.side_effect = RuntimeError("boom")
        result = generate_codebase_summary(project, config=object())
        assert result == ""

    @patch("auto_sdd.lib.codebase_summary._call_agent")
    @patch("auto_sdd.lib.codebase_summary._get_tree_hash")
    def test_learnings_appended(
        self, mock_hash: MagicMock, mock_agent: MagicMock, project: Path,
    ) -> None:
        mock_hash.return_value = "abc"
        mock_agent.return_value = "agent summary"
        ld = project / ".specs" / "learnings"
        ld.mkdir(parents=True)
        (ld / "tips.md").write_text("use tokens\n")
        result = generate_codebase_summary(project, config=object())
        assert "agent summary" in result
        assert "use tokens" in result
