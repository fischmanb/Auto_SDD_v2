"""Tests for reliability.py — locking and resume state."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from auto_sdd.lib.reliability import (
    ResumeState, LockError,
    acquire_lock, release_lock, _lock_fds,
    read_state, write_state, clean_state,
    new_campaign_id, _logs_dir,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Fake project directory with logs/."""
    (tmp_path / "logs").mkdir()
    return tmp_path


# ── Locking ──────────────────────────────────────────────────────────────────


class TestAcquireLock:
    """Tests for acquire_lock / release_lock."""

    def test_creates_lock_file(self, project: Path) -> None:
        acquire_lock(project)
        try:
            lock = _logs_dir(project) / ".build-lock"
            assert lock.exists()
        finally:
            release_lock(project)

    def test_lock_contains_our_pid(self, project: Path) -> None:
        acquire_lock(project)
        try:
            lock = _logs_dir(project) / ".build-lock"
            pid_str = lock.read_text().strip()
            assert pid_str == str(os.getpid())
        finally:
            release_lock(project)

    def test_release_removes_file(self, project: Path) -> None:
        acquire_lock(project)
        release_lock(project)
        lock = _logs_dir(project) / ".build-lock"
        assert not lock.exists()

    def test_release_cleans_fd_tracking(self, project: Path) -> None:
        acquire_lock(project)
        lock = _logs_dir(project) / ".build-lock"
        assert str(lock) in _lock_fds
        release_lock(project)
        assert str(lock) not in _lock_fds

    def test_stale_lock_reclaimed(self, project: Path) -> None:
        """Dead PID in lock file gets replaced with ours."""
        lock = _logs_dir(project) / ".build-lock"
        lock.write_text("99999999\n")  # PID that doesn't exist
        acquire_lock(project)
        try:
            pid_str = lock.read_text().strip()
            assert pid_str == str(os.getpid())
        finally:
            release_lock(project)

    def test_live_lock_raises(self, project: Path) -> None:
        """Lock held by our own process raises LockError."""
        acquire_lock(project)
        try:
            with pytest.raises(LockError, match="already running"):
                acquire_lock(project)
        finally:
            release_lock(project)

    def test_corrupt_lock_cleaned(self, project: Path) -> None:
        """Non-numeric content in lock file gets cleaned up."""
        lock = _logs_dir(project) / ".build-lock"
        lock.write_text("not-a-pid\n")
        acquire_lock(project)
        try:
            pid_str = lock.read_text().strip()
            assert pid_str == str(os.getpid())
        finally:
            release_lock(project)

    def test_release_noop_no_lock(self, project: Path) -> None:
        """Release with no lock file doesn't error."""
        release_lock(project)  # should not raise

    def test_creates_logs_dir(self, tmp_path: Path) -> None:
        """acquire_lock creates logs/ if missing."""
        acquire_lock(tmp_path)
        try:
            assert (tmp_path / "logs").is_dir()
        finally:
            release_lock(tmp_path)


# ── Resume state ─────────────────────────────────────────────────────────────


class TestResumeState:
    """Tests for ResumeState dataclass."""

    def test_to_dict_roundtrip(self) -> None:
        state = ResumeState(
            campaign_id="20260315-120000",
            completed=["Auth", "Dashboard"],
            current="Settings",
            started_at="2026-03-15T12:00:00Z",
        )
        d = state.to_dict()
        restored = ResumeState.from_dict(d)
        assert restored.campaign_id == state.campaign_id
        assert restored.completed == state.completed
        assert restored.current == state.current
        assert restored.started_at == state.started_at

    def test_from_dict_defaults(self) -> None:
        state = ResumeState.from_dict({})
        assert state.campaign_id == ""
        assert state.completed == []
        assert state.current == ""
        assert state.started_at == ""


class TestWriteReadState:
    """Tests for write_state / read_state."""

    def test_write_then_read(self, project: Path) -> None:
        state = ResumeState(
            campaign_id="test-001",
            completed=["Auth", "Dashboard"],
            current="Settings",
            started_at="2026-03-15T12:00:00Z",
        )
        write_state(project, state)
        restored = read_state(project)
        assert restored is not None
        assert restored.campaign_id == "test-001"
        assert restored.completed == ["Auth", "Dashboard"]
        assert restored.current == "Settings"

    def test_write_overwrites_existing(self, project: Path) -> None:
        s1 = ResumeState(campaign_id="old", completed=["A"])
        s2 = ResumeState(campaign_id="new", completed=["A", "B"])
        write_state(project, s1)
        write_state(project, s2)
        restored = read_state(project)
        assert restored is not None
        assert restored.campaign_id == "new"
        assert len(restored.completed) == 2

    def test_read_missing_returns_none(self, project: Path) -> None:
        assert read_state(project) is None

    def test_read_corrupt_returns_none(self, project: Path) -> None:
        state_path = project / "logs" / "resume-state.json"
        state_path.write_text("not valid json{{{")
        assert read_state(project) is None

    def test_write_creates_valid_json(self, project: Path) -> None:
        state = ResumeState(campaign_id="test")
        write_state(project, state)
        state_path = project / "logs" / "resume-state.json"
        data = json.loads(state_path.read_text())
        assert data["campaign_id"] == "test"

    def test_write_special_chars(self, project: Path) -> None:
        """Feature names with special characters survive roundtrip."""
        state = ResumeState(
            campaign_id="test",
            completed=['Auth: "Signup"', "Dashboard (v2)"],
        )
        write_state(project, state)
        restored = read_state(project)
        assert restored is not None
        assert restored.completed[0] == 'Auth: "Signup"'
        assert restored.completed[1] == "Dashboard (v2)"


class TestCleanState:
    """Tests for clean_state."""

    def test_removes_file(self, project: Path) -> None:
        state = ResumeState(campaign_id="test")
        write_state(project, state)
        state_path = project / "logs" / "resume-state.json"
        assert state_path.exists()
        clean_state(project)
        assert not state_path.exists()

    def test_missing_noop(self, project: Path) -> None:
        clean_state(project)  # should not raise


class TestNewCampaignId:
    """Tests for new_campaign_id."""

    def test_format(self) -> None:
        cid = new_campaign_id()
        # Format: YYYYMMDD-HHMMSS
        assert len(cid) == 15
        assert cid[8] == "-"
        # All other chars are digits
        assert cid[:8].isdigit()
        assert cid[9:].isdigit()
