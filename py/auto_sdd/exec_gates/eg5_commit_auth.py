"""EG5: Commit Auth ExecGate — final check before HEAD advances.

After all mechanical gates pass (EG2 signals, EG3 build, EG4 tests),
this is the last deterministic check before the loop state changes
become irreversible. Validates:

    1. HEAD actually advanced (agent committed something)
    2. Working tree is clean (no uncommitted changes left behind)
    3. No files outside project scope were touched (contamination)
    4. Test count did not regress (if baseline provided)

This gate runs AFTER EG3 (build) and EG4 (test) — it
catches state-level issues that build gates don't cover.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from auto_sdd.lib.types import GateError

logger = logging.getLogger(__name__)


# ── Result type ──────────────────────────────────────────────────────────────


@dataclass
class CommitAuthResult:
    """Result of the commit authorization gate."""

    authorized: bool = False
    checks_passed: list[GateError] = field(default_factory=list)
    checks_failed: list[GateError] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.authorized:
            return f"Authorized ({len(self.checks_passed)} checks passed)"
        failed_codes = ", ".join(e.code for e in self.checks_failed)
        return (
            f"Blocked ({len(self.checks_failed)} failed: "
            f"{failed_codes})"
        )

    def to_dict(self) -> dict:
        return {
            "authorized": self.authorized,
            "checks_passed": [{"code": e.code, "detail": e.detail} for e in self.checks_passed],
            "checks_failed": [{"code": e.code, "detail": e.detail} for e in self.checks_failed],
            "summary": self.summary,
        }


# ── Individual checks ────────────────────────────────────────────────────────


def _get_head(project_dir: Path) -> str:
    """Get current HEAD commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True,
            cwd=str(project_dir), timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def _check_head_advanced(
    project_dir: Path,
    branch_start_commit: str,
) -> tuple[bool, GateError]:
    """Check 1: HEAD must have advanced past the starting commit."""
    if not branch_start_commit:
        return True, GateError("HEAD_ADVANCED", "no baseline — skipped")

    head_now = _get_head(project_dir)
    if not head_now:
        return False, GateError("HEAD_ADVANCED", "could not read HEAD")
    if head_now == branch_start_commit:
        return False, GateError("HEAD_UNCHANGED", "HEAD unchanged — agent made no commits")
    return True, GateError("HEAD_ADVANCED", "ok")


def _check_tree_clean(project_dir: Path) -> tuple[bool, GateError]:
    """Check 2: No tracked modifications or staged changes remain."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True,
            cwd=str(project_dir), timeout=10,
        )
        if result.returncode != 0:
            return False, GateError("TREE_DIRTY", "git status failed")

        lines = [line for line in result.stdout.splitlines() if line.strip()]

        # Warn on untracked files (don't fail — could be build artifacts)
        untracked = [line for line in lines if line.startswith("??")]
        if untracked:
            logger.warning(
                "EG5: %d untracked file(s) after agent finished: %s",
                len(untracked),
                ", ".join(line[3:] for line in untracked[:5]),
            )

        # Filter to tracked changes only (ignore untracked '??')
        dirty = [line for line in lines if not line.startswith("??")]
        if dirty:
            return False, GateError("TREE_DIRTY", f"{len(dirty)} uncommitted change(s)")
        return True, GateError("TREE_CLEAN", "ok")
    except (subprocess.TimeoutExpired, OSError):
        return False, GateError("TREE_DIRTY", "git status error")


def _check_no_contamination(
    project_dir: Path,
    branch_start_commit: str,
) -> tuple[bool, GateError]:
    """Check 3: No files outside project root were modified."""
    if not branch_start_commit:
        return True, GateError("NO_CONTAMINATION", "no baseline — skipped")

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", branch_start_commit, "HEAD"],
            capture_output=True, text=True,
            cwd=str(project_dir), timeout=30,
        )
        if result.returncode != 0:
            return False, GateError("CONTAMINATION", "git diff failed")

        resolved_root = project_dir.resolve()
        contaminated: list[str] = []
        for line in result.stdout.strip().splitlines():
            path = line.strip()
            if not path:
                continue
            full = (project_dir / path).resolve()
            try:
                full.relative_to(resolved_root)
            except ValueError:
                contaminated.append(path)

        if contaminated:
            return False, GateError(
                "CONTAMINATION",
                f"{len(contaminated)} file(s) outside root: "
                f"{', '.join(contaminated[:3])}",
            )
        return True, GateError("NO_CONTAMINATION", "ok")
    except (subprocess.TimeoutExpired, OSError):
        return False, GateError("CONTAMINATION", "git diff error")


def _check_test_regression(
    current_test_count: int | None,
    baseline_test_count: int | None,
) -> tuple[bool, GateError]:
    """Check 4: Test count did not decrease from baseline."""
    if baseline_test_count is None or current_test_count is None:
        return True, GateError("TEST_REGRESSION", "no baseline — skipped")

    if current_test_count < baseline_test_count:
        return False, GateError(
            "TEST_REGRESSION",
            f"count dropped: {baseline_test_count} → {current_test_count}",
        )
    return True, GateError("TEST_REGRESSION", f"{current_test_count} >= {baseline_test_count}")


# ── Main gate ────────────────────────────────────────────────────────────────


def authorize_commit(
    project_dir: Path,
    branch_start_commit: str = "",
    current_test_count: int | None = None,
    baseline_test_count: int | None = None,
) -> CommitAuthResult:
    """Run all commit authorization checks.

    This is the EG5 gate — the final deterministic check before
    the loop state advances. Returns CommitAuthResult with the
    overall decision and per-check details.

    Args:
        project_dir: Project root directory.
        branch_start_commit: HEAD at branch creation. If empty,
            head_advanced and contamination checks are skipped.
        current_test_count: Test count from the current build gate run.
        baseline_test_count: Test count before this feature was built.
    """
    result = CommitAuthResult()

    checks = [
        _check_head_advanced(project_dir, branch_start_commit),
        _check_tree_clean(project_dir),
        _check_no_contamination(project_dir, branch_start_commit),
        _check_test_regression(current_test_count, baseline_test_count),
    ]

    for passed, gate_error in checks:
        if passed:
            result.checks_passed.append(gate_error)
        else:
            result.checks_failed.append(gate_error)

    result.authorized = len(result.checks_failed) == 0

    if result.authorized:
        logger.info("EG5 commit authorized: %s", result.summary)
    else:
        logger.warning("EG5 commit BLOCKED: %s", result.summary)

    return result
