"""Resume state and campaign locking for the build loop.

Resume: after each successful feature build, persist which features are
done. On crash recovery, skip completed features. On clean campaign
completion, remove the state file.

Locking: fcntl.flock() + PID-based stale detection prevents concurrent
loops on the same project. Matches v1 reliability.py pattern.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# File locations within project_dir/logs/
_LOCK_FILE = ".build-lock"
_STATE_FILE = "resume-state.json"


# Module-level dict to track open lock file descriptors by path.
_lock_fds: dict[str, int] = {}


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


class LockError(Exception):
    """Raised when the campaign lock cannot be acquired."""
    pass


def _logs_dir(project_dir: Path) -> Path:
    d = project_dir / "logs"
    d.mkdir(exist_ok=True)
    return d


# ── Locking (fcntl.flock + PID stale detection) ─────────────────────────────


def acquire_lock(project_dir: Path) -> Path:
    """Acquire the campaign lock. Raises LockError if already locked.

    Uses fcntl.flock() for OS-level locking AND writes PID to the file
    for stale-lock detection by other processes.

    If a lock file exists with a dead PID, reclaims it automatically.
    """
    lock_path = _logs_dir(project_dir) / _LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Check for existing lock file with PID-based stale detection
    if lock_path.exists():
        try:
            existing_pid_str = lock_path.read_text().strip()
            if existing_pid_str:
                existing_pid = int(existing_pid_str)
                try:
                    os.kill(existing_pid, 0)
                    # Process is alive — lock is held
                    raise LockError(
                        f"Build loop already running (PID {existing_pid}). "
                        f"Lock file: {lock_path}"
                    )
                except ProcessLookupError:
                    # Process is dead — stale lock
                    logger.warning(
                        "Reclaiming stale lock from dead PID %d",
                        existing_pid,
                    )
                    lock_path.unlink(missing_ok=True)
                except PermissionError:
                    # Process exists but we can't signal it
                    raise LockError(
                        f"Build loop running as different user (PID {existing_pid}). "
                        f"Lock file: {lock_path}"
                    )
        except (ValueError, FileNotFoundError):
            # Corrupt or vanished lock file — clean up
            lock_path.unlink(missing_ok=True)

    # Create lock file with our PID and acquire flock
    fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise LockError(f"Could not acquire flock on {lock_path}")

    os.write(fd, f"{os.getpid()}\n".encode())
    os.fsync(fd)
    _lock_fds[str(lock_path)] = fd

    logger.info("Campaign lock acquired: %s (PID %d)", lock_path, os.getpid())
    return lock_path


def release_lock(project_dir: Path) -> None:
    """Release the campaign lock. No-op if no lock exists."""
    lock_path = _logs_dir(project_dir) / _LOCK_FILE
    key = str(lock_path)
    fd = _lock_fds.pop(key, None)
    if fd is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
    lock_path.unlink(missing_ok=True)
    logger.info("Campaign lock released")


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
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        logger.warning("Corrupt resume state, ignoring: %s", exc)
        return None


def write_state(project_dir: Path, state: ResumeState) -> None:
    """Persist resume state to disk. Atomic via tempfile + rename."""
    state_path = _logs_dir(project_dir) / _STATE_FILE
    state_path.parent.mkdir(parents=True, exist_ok=True)

    data = json.dumps(state.to_dict(), indent=2) + "\n"

    fd, tmp_path = tempfile.mkstemp(
        dir=str(state_path.parent), prefix=state_path.stem,
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
        os.rename(tmp_path, str(state_path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def clean_state(project_dir: Path) -> None:
    """Remove resume state file. Called after successful campaign."""
    state_path = _logs_dir(project_dir) / _STATE_FILE
    state_path.unlink(missing_ok=True)
    logger.info("Resume state cleaned (campaign complete)")


def new_campaign_id() -> str:
    """Generate a campaign ID from the current timestamp."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
