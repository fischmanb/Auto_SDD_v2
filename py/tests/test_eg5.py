"""Tests for EG5: Commit Auth ExecGate."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from auto_sdd.exec_gates.eg5_commit_auth import (
    CommitAuthResult,
    _check_head_advanced,
    _check_no_contamination,
    _check_test_regression,
    _check_tree_clean,
    _get_head,
    authorize_commit,
)


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, check=True)


@pytest.fixture
def git_project(tmp_path: Path) -> Path:
    """Create a minimal git project with one commit."""
    _git(["init"], tmp_path)
    _git(["config", "user.email", "test@test.com"], tmp_path)
    _git(["config", "user.name", "Test"], tmp_path)
    _git(["config", "commit.gpgsign", "false"], tmp_path)
    (tmp_path / "initial.txt").write_text("initial\n")
    _git(["add", "."], tmp_path)
    _git(["commit", "-m", "initial"], tmp_path)
    return tmp_path


class TestGetHead:
    def test_returns_commit_hash(self, git_project: Path) -> None:
        head = _get_head(git_project)
        assert len(head) == 40  # SHA-1 hex

    def test_returns_empty_for_non_git(self, tmp_path: Path) -> None:
        assert _get_head(tmp_path) == ""


class TestCheckHeadAdvanced:
    def test_head_advanced(self, git_project: Path) -> None:
        start = _get_head(git_project)
        (git_project / "new.txt").write_text("new\n")
        _git(["add", "."], git_project)
        _git(["commit", "-m", "new"], git_project)
        ok, err = _check_head_advanced(git_project, start)
        assert ok is True
        assert err.code == "HEAD_ADVANCED"

    def test_head_not_advanced(self, git_project: Path) -> None:
        start = _get_head(git_project)
        ok, err = _check_head_advanced(git_project, start)
        assert ok is False
        assert err.code == "HEAD_UNCHANGED"

    def test_no_baseline_skips(self, git_project: Path) -> None:
        ok, err = _check_head_advanced(git_project, "")
        assert ok is True
        assert "skipped" in err.detail


class TestCheckTreeClean:
    def test_clean_tree(self, git_project: Path) -> None:
        ok, err = _check_tree_clean(git_project)
        assert ok is True

    def test_dirty_tree(self, git_project: Path) -> None:
        (git_project / "initial.txt").write_text("modified\n")
        ok, err = _check_tree_clean(git_project)
        assert ok is False
        assert err.code == "TREE_DIRTY"

    def test_untracked_files_ignored(self, git_project: Path) -> None:
        """Untracked files are not considered dirty (warning only)."""
        (git_project / "untracked.txt").write_text("new\n")
        ok, err = _check_tree_clean(git_project)
        assert ok is True


class TestCheckTestRegression:
    def test_no_regression(self) -> None:
        ok, err = _check_test_regression(current_test_count=15, baseline_test_count=10)
        assert ok is True
        assert "15 >= 10" in err.detail

    def test_regression_detected(self) -> None:
        ok, err = _check_test_regression(current_test_count=8, baseline_test_count=10)
        assert ok is False
        assert err.code == "TEST_REGRESSION"
        assert "dropped" in err.detail

    def test_equal_passes(self) -> None:
        ok, err = _check_test_regression(current_test_count=10, baseline_test_count=10)
        assert ok is True

    def test_no_baseline_skips(self) -> None:
        ok, err = _check_test_regression(current_test_count=10, baseline_test_count=None)
        assert ok is True
        assert "skipped" in err.detail

    def test_no_current_skips(self) -> None:
        ok, err = _check_test_regression(current_test_count=None, baseline_test_count=10)
        assert ok is True
        assert "skipped" in err.detail


class TestAuthorizeCommit:
    def test_all_pass(self, git_project: Path) -> None:
        start = _get_head(git_project)
        (git_project / "feature.ts").write_text("export const x = 1;\n")
        _git(["add", "."], git_project)
        _git(["commit", "-m", "feat"], git_project)
        result = authorize_commit(
            project_dir=git_project,
            branch_start_commit=start,
            current_test_count=12,
            baseline_test_count=10,
        )
        assert result.authorized is True
        assert len(result.checks_failed) == 0
        assert len(result.checks_passed) == 4

    def test_head_not_advanced_blocks(self, git_project: Path) -> None:
        start = _get_head(git_project)
        result = authorize_commit(
            project_dir=git_project,
            branch_start_commit=start,
        )
        assert result.authorized is False
        assert any(e.code == "HEAD_UNCHANGED" for e in result.checks_failed)

    def test_dirty_tree_blocks(self, git_project: Path) -> None:
        start = _get_head(git_project)
        (git_project / "feature.ts").write_text("export const x = 1;\n")
        _git(["add", "."], git_project)
        _git(["commit", "-m", "feat"], git_project)
        # Leave tracked file modified
        (git_project / "feature.ts").write_text("modified\n")
        result = authorize_commit(
            project_dir=git_project,
            branch_start_commit=start,
        )
        assert result.authorized is False
        assert any(e.code == "TREE_DIRTY" for e in result.checks_failed)

    def test_regression_blocks(self, git_project: Path) -> None:
        start = _get_head(git_project)
        (git_project / "f.ts").write_text("x\n")
        _git(["add", "."], git_project)
        _git(["commit", "-m", "feat"], git_project)
        result = authorize_commit(
            project_dir=git_project,
            branch_start_commit=start,
            current_test_count=5,
            baseline_test_count=10,
        )
        assert result.authorized is False
        assert any(e.code == "TEST_REGRESSION" for e in result.checks_failed)

    def test_summary_property(self) -> None:
        from auto_sdd.lib.types import GateError
        r = CommitAuthResult(
            authorized=True,
            checks_passed=[GateError("A"), GateError("B"), GateError("C")],
            checks_failed=[],
        )
        assert "Authorized" in r.summary
        assert "3" in r.summary

    def test_to_dict(self) -> None:
        from auto_sdd.lib.types import GateError
        r = CommitAuthResult(
            authorized=False,
            checks_passed=[GateError("A", "ok")],
            checks_failed=[GateError("B", "failed")],
        )
        d = r.to_dict()
        assert d["authorized"] is False
        assert d["checks_failed"][0]["code"] == "B"
        assert "summary" in d
