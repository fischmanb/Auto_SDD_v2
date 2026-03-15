"""Tests for branch_manager.py — feature branch lifecycle."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from auto_sdd.lib.branch_manager import (
    BranchError, BranchSetupResult,
    setup_feature_branch, merge_feature_branch,
    delete_feature_branch, cleanup_merged_branches,
    get_current_branch, _run_git,
)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a real git repo with one commit on main."""
    env = {**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"}

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(tmp_path), *args],
            capture_output=True, check=True, env=env,
        )

    git("init", "-b", "main")
    (tmp_path / "README.md").write_text("# test\n")
    git("add", "-A")
    git("commit", "-m", "initial")
    return tmp_path


# ── Setup ────────────────────────────────────────────────────────────────────


class TestSetupFeatureBranch:

    def test_creates_branch(self, git_repo: Path) -> None:
        result = setup_feature_branch(git_repo, "main")
        assert result.branch_name.startswith("auto/feature-")

    def test_switches_to_new_branch(self, git_repo: Path) -> None:
        result = setup_feature_branch(git_repo, "main")
        assert get_current_branch(git_repo) == result.branch_name

    def test_branches_from_main(self, git_repo: Path) -> None:
        """New branch HEAD matches main HEAD."""
        main_head = _run_git(["rev-parse", "HEAD"], git_repo).stdout.strip()
        result = setup_feature_branch(git_repo, "main")
        branch_head = _run_git(["rev-parse", "HEAD"], git_repo).stdout.strip()
        assert branch_head == main_head

    def test_stashes_dirty_state(self, git_repo: Path) -> None:
        """Dirty working tree doesn't block branch creation."""
        (git_repo / "dirty.txt").write_text("uncommitted")
        result = setup_feature_branch(git_repo, "main")
        assert result.branch_name.startswith("auto/feature-")

    def test_error_on_bad_main_branch(self, git_repo: Path) -> None:
        with pytest.raises(BranchError):
            setup_feature_branch(git_repo, "nonexistent-branch")


# ── Merge ────────────────────────────────────────────────────────────────────


class TestMergeFeatureBranch:

    def _setup_and_commit(self, git_repo: Path) -> str:
        """Create feature branch with a commit, return branch name."""
        env = {**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"}
        result = setup_feature_branch(git_repo, "main")
        (git_repo / "feature.txt").write_text("new feature\n")
        subprocess.run(
            ["git", "-C", str(git_repo), "add", "-A"],
            capture_output=True, check=True, env=env,
        )
        subprocess.run(
            ["git", "-C", str(git_repo), "commit", "-m", "feat"],
            capture_output=True, check=True, env=env,
        )
        return result.branch_name

    def test_merge_switches_to_main(self, git_repo: Path) -> None:
        branch = self._setup_and_commit(git_repo)
        merge_feature_branch(git_repo, branch, "main")
        assert get_current_branch(git_repo) == "main"

    def test_merge_includes_commit(self, git_repo: Path) -> None:
        branch = self._setup_and_commit(git_repo)
        merge_feature_branch(git_repo, branch, "main")
        assert (git_repo / "feature.txt").exists()

    def test_merge_deletes_branch(self, git_repo: Path) -> None:
        branch = self._setup_and_commit(git_repo)
        merge_feature_branch(git_repo, branch, "main")
        branches = _run_git(["branch"], git_repo).stdout
        assert branch not in branches

    def test_merge_no_ff(self, git_repo: Path) -> None:
        """Merge commit exists (--no-ff)."""
        branch = self._setup_and_commit(git_repo)
        merge_feature_branch(git_repo, branch, "main")
        log = _run_git(["log", "--oneline", "-1"], git_repo).stdout
        assert "Merge" in log


# ── Delete ───────────────────────────────────────────────────────────────────


class TestDeleteFeatureBranch:

    def test_deletes_branch(self, git_repo: Path) -> None:
        result = setup_feature_branch(git_repo, "main")
        delete_feature_branch(git_repo, result.branch_name, "main")
        branches = _run_git(["branch"], git_repo).stdout
        assert result.branch_name not in branches

    def test_switches_to_main(self, git_repo: Path) -> None:
        result = setup_feature_branch(git_repo, "main")
        delete_feature_branch(git_repo, result.branch_name, "main")
        assert get_current_branch(git_repo) == "main"

    def test_noop_on_missing_branch(self, git_repo: Path) -> None:
        """Deleting a nonexistent branch doesn't raise."""
        delete_feature_branch(git_repo, "auto/nonexistent", "main")


# ── Cleanup merged ───────────────────────────────────────────────────────────


class TestCleanupMergedBranches:

    def test_cleans_merged_auto_branches(self, git_repo: Path) -> None:
        """Merged auto/ branches are deleted."""
        env = {**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"}
        result = setup_feature_branch(git_repo, "main")
        (git_repo / "f.txt").write_text("x\n")
        subprocess.run(
            ["git", "-C", str(git_repo), "add", "-A"],
            capture_output=True, check=True, env=env,
        )
        subprocess.run(
            ["git", "-C", str(git_repo), "commit", "-m", "feat"],
            capture_output=True, check=True, env=env,
        )
        merge_feature_branch(git_repo, result.branch_name, "main")
        # Branch already deleted by merge, create another merged one
        result2 = setup_feature_branch(git_repo, "main")
        # No new commits — fast-forward merge
        _run_git(["checkout", "main"], git_repo)
        _run_git(["merge", result2.branch_name], git_repo)
        count = cleanup_merged_branches(git_repo, "main")
        assert count >= 1

    def test_returns_zero_when_none(self, git_repo: Path) -> None:
        assert cleanup_merged_branches(git_repo, "main") == 0


# ── get_current_branch ───────────────────────────────────────────────────────


class TestGetCurrentBranch:

    def test_returns_main(self, git_repo: Path) -> None:
        assert get_current_branch(git_repo) == "main"

    def test_returns_feature_branch(self, git_repo: Path) -> None:
        result = setup_feature_branch(git_repo, "main")
        assert get_current_branch(git_repo) == result.branch_name
