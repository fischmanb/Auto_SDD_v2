"""Resume state and campaign locking for the build loop.

Resume: after each successful feature build, persist which features are
done. On crash recovery, skip completed features. On clean campaign
completion, remove the state file.

Locking: PID-based lockfile prevents concurrent loops on the same project.
Stale locks (dead PID) are automatically reclaimed.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# File locations within project_dir/logs/
_LOCK_FILE = ".build-lock"
_STATE_FILE = "resume-state.json"


@dataclass
class ResumeState:
    """Persistent state for crash recovery.

    Serialized to logs/resume-state.json after each successful feature.
    """
    campaign_id: str = ""
    completed: list[str] = field(default_factory=list)
    current: str = ""
    started_at: str = ""

    def to_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "completed": self.completed,
            "current": self.current,
            "started_at": self.started_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ResumeState:
        return cls(
            campaign_id=data.get("campaign_id", ""),
            completed=data.get("completed", []),
            current=data.get("current", ""),
            started_at=data.get("started_at", ""),
        )


def _logs_dir(project_dir: Path) -> Path:
    d = project_dir / "logs"
    d.mkdir(exist_ok=True)
    return d


def _pid_alive(pid: int) -> bool:
    """Check if a process is still running."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it — treat as alive.
        return True


# ── Locking ──────────────────────────────────────────────────────────────────


class LockError(Exception):
    """Raised when the campaign lock cannot be acquired."""
    pass


def acquire_lock(project_dir: Path) -> Path:
    """Acquire the campaign lock. Raises LockError if already locked.

    Creates logs/.build-lock containing the current PID.
    If a lock exists but the PID is dead, reclaims it (stale lock).
    """
    lock_path = _logs_dir(project_dir) / _LOCK_FILE

    if lock_path.exists():
        try:
            existing_pid = int(lock_path.read_text().strip())
        except (ValueError, OSError):
            existing_pid = -1

        if _pid_alive(existing_pid):
            raise LockError(
                f"Build loop already running (PID {existing_pid}). "
                f"Lock file: {lock_path}"
            )
        logger.warning(
            "Reclaiming stale lock from dead PID %d", existing_pid,
        )

    lock_path.write_text(str(os.getpid()))
    logger.info("Campaign lock acquired: %s", lock_path)
    return lock_path


def release_lock(project_dir: Path) -> None:
    """Release the campaign lock. No-op if no lock exists."""
    lock_path = _logs_dir(project_dir) / _LOCK_FILE
    if lock_path.exists():
        try:
            lock_path.unlink()
            logger.info("Campaign lock released")
        except OSError as exc:
            logger.warning("Failed to release lock: %s", exc)


# ── Resume state ─────────────────────────────────────────────────────────────


def read_state(project_dir: Path) -> ResumeState | None:
    """Read resume state from disk. Returns None if no state file."""
    state_path = _logs_dir(project_dir) / _STATE_FILE
    if not state_path.exists():
        return None
    try:
        data = json.loads(state_path.read_text())
        state = ResumeState.from_dict(data)
        logger.info(
            "Resumed state: campaign=%s, %d completed",
            state.campaign_id, len(state.completed),
        )
        return state
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Corrupt resume state, ignoring: %s", exc)
        return None


def write_state(project_dir: Path, state: ResumeState) -> None:
    """Persist resume state to disk. Atomic via write-then-rename."""
    state_path = _logs_dir(project_dir) / _STATE_FILE
    tmp_path = state_path.with_suffix(".tmp")
    try:
        tmp_path.write_text(json.dumps(state.to_dict(), indent=2) + "\n")
        tmp_path.replace(state_path)
    except OSError as exc:
        logger.warning("Failed to write resume state: %s", exc)


def clean_state(project_dir: Path) -> None:
    """Remove resume state file. Called after successful campaign."""
    state_path = _logs_dir(project_dir) / _STATE_FILE
    if state_path.exists():
        try:
            state_path.unlink()
            logger.info("Resume state cleaned (campaign complete)")
        except OSError as exc:
            logger.warning("Failed to clean resume state: %s", exc)


def new_campaign_id() -> str:
    """Generate a campaign ID from the current timestamp."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
