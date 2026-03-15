"""Branch management for the V2 build loop.

V2 uses chained strategy only: each feature branches from the previous
feature's branch (or main for the first feature). On success, the branch
is merged to main. On failure, it's deleted.

Independent and sequential strategies are stripped per P6. Re-add if
needed after first campaign.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class BranchError(Exception):
    """Failed to create, switch, or merge a branch."""
    pass


@dataclass
class BranchSetupResult:
    """Result of a branch setup operation."""
    branch_name: str


# ── Helpers ──────────────────────────────────────────────────────────────────


def _run_git(
    args: list[str],
    project_dir: Path,
    *,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Run a git command in project_dir."""
    return subprocess.run(
        ["git", "-C", str(project_dir), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _timestamp_suffix() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def get_current_branch(project_dir: Path) -> str:
    """Return the current branch name, or 'main' if detached."""
    result = _run_git(["branch", "--show-current"], project_dir)
    return result.stdout.strip() or "main"


# ── Branch setup ─────────────────────────────────────────────────────────────


def setup_feature_branch(
    project_dir: Path,
    main_branch: str = "main",
) -> BranchSetupResult:
    """Create a feature branch from main for the next build.

    Each feature branches from main (which accumulates merged successes).
    Stashes dirty state before switching.

    Raises:
        BranchError: If branch creation fails.
    """
    # Stash to prevent dirty worktree issues
    _run_git(["add", "-A"], project_dir)
    _run_git(
        ["stash", "push", "-m", "auto-stash before feature branch"],
        project_dir,
    )

    # Ensure we're on main
    checkout = _run_git(["checkout", main_branch], project_dir)
    if checkout.returncode != 0:
        raise BranchError(
            f"Failed to checkout {main_branch}: {checkout.stderr}"
        )

    branch_name = f"auto/feature-{_timestamp_suffix()}"
    create = _run_git(["checkout", "-b", branch_name], project_dir)
    if create.returncode != 0:
        raise BranchError(
            f"Failed to create branch {branch_name}: {create.stderr}"
        )

    logger.info("Created feature branch: %s (from %s)", branch_name, main_branch)
    return BranchSetupResult(branch_name=branch_name)


# ── Branch merge/cleanup ─────────────────────────────────────────────────────


def merge_feature_branch(
    project_dir: Path,
    branch_name: str,
    main_branch: str = "main",
) -> None:
    """Merge a successful feature branch into main and delete it.

    Uses --no-ff to preserve branch history in the merge commit.

    Raises:
        BranchError: If merge or cleanup fails.
    """
    checkout = _run_git(["checkout", main_branch], project_dir)
    if checkout.returncode != 0:
        raise BranchError(
            f"Failed to checkout {main_branch} for merge: {checkout.stderr}"
        )

    merge = _run_git(
        ["merge", "--no-ff", branch_name, "-m",
         f"Merge {branch_name} into {main_branch}"],
        project_dir,
    )
    if merge.returncode != 0:
        raise BranchError(
            f"Failed to merge {branch_name}: {merge.stderr}"
        )

    # Delete the feature branch
    _run_git(["branch", "-d", branch_name], project_dir)
    logger.info("Merged and deleted: %s → %s", branch_name, main_branch)


def delete_feature_branch(
    project_dir: Path,
    branch_name: str,
    main_branch: str = "main",
) -> None:
    """Delete a failed feature branch without merging.

    Checks out main first, then force-deletes the branch.
    """
    _run_git(["checkout", main_branch], project_dir)
    result = _run_git(["branch", "-D", branch_name], project_dir)
    if result.returncode != 0:
        logger.warning(
            "Failed to delete branch %s: %s", branch_name, result.stderr,
        )
    else:
        logger.info("Deleted failed branch: %s", branch_name)


def cleanup_merged_branches(
    project_dir: Path,
    main_branch: str = "main",
) -> int:
    """Delete any merged auto/* branches. Returns count deleted."""
    result = _run_git(["branch", "--merged", main_branch], project_dir)
    if result.returncode != 0:
        return 0

    count = 0
    for line in result.stdout.splitlines():
        branch = line.strip().lstrip("* ")
        if branch.startswith("auto/"):
            del_result = _run_git(["branch", "-d", branch], project_dir)
            if del_result.returncode == 0:
                count += 1
                logger.info("Cleaned up merged branch: %s", branch)

    return count
