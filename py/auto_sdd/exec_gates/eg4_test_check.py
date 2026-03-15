"""EG4: Test Check ExecGate — orchestrator-side test verification.

Runs the project's test command as a subprocess, captures pass/fail,
and parses test count from common framework output formats.
The agent never runs tests — this is the orchestrator's job (P1).
Deterministic: subprocess exit code + mechanical count extraction.

Also provides detect_test_cmd() for auto-detecting the correct test
command from project files.

AgentSpec lineage: agent_finish trigger, deterministic predicate
(exit code check + count parse), binary enforce (pass/fail).
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TestCheckResult:
    """Result of the EG4 test check."""

    passed: bool = False
    test_count: int | None = None
    output: str = ""
    skipped: bool = False

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "test_count": self.test_count,
            "output": self.output,
            "skipped": self.skipped,
        }


def _parse_test_count(output: str) -> int | None:
    """Extract test count from common framework output formats.

    Supports:
        - Jest/Vitest: "Tests: X passed" or "Tests X passed"
        - Pytest: "X passed" (with optional context like "in 3.2s")
        - Mocha: "X passing"
        - Cargo test: "test result: ok. X passed"
        - Go test (verbose): counts "--- PASS:" lines

    Returns None if no count can be parsed.
    """
    # Jest/Vitest: "Tests: 42 passed" or "Tests 42 passed, 0 failed"
    m = re.search(r'Tests:?\s+(\d+)\s+passed', output)
    if m:
        return int(m.group(1))
    # Mocha: "42 passing (3s)" or "42 passing"
    m = re.search(r'(\d+)\s+passing', output)
    if m:
        return int(m.group(1))
    # Cargo test: "test result: ok. 42 passed; 0 failed"
    m = re.search(r'test result:.*?(\d+)\s+passed', output)
    if m:
        return int(m.group(1))
    # Go test verbose: count "--- PASS:" lines
    go_passes = re.findall(r'--- PASS:', output)
    if go_passes:
        return len(go_passes)
    # Pytest: "42 passed" (generic, last resort to avoid false matches)
    m = re.search(r'(\d+)\s+passed', output)
    if m:
        return int(m.group(1))
    return None


def check_tests(test_cmd: str, project_dir: Path) -> TestCheckResult:
    """Run the project test command (orchestrator-side, per P1).

    This is EG4 — deterministic test verification. The agent cannot
    run tests or report test results. The orchestrator captures the
    exit code, output, and parsed test count directly.

    Args:
        test_cmd: Shell command to run (e.g., 'npm test').
            If empty or 'skip', returns a skipped result.
        project_dir: Project root directory (cwd for the subprocess).

    Returns:
        TestCheckResult with passed, test_count, output, and skipped.
    """
    if not test_cmd or test_cmd == "skip":
        logger.debug("EG4 test check skipped (no test command)")
        return TestCheckResult(
            passed=True, output="(test check skipped)", skipped=True,
        )

    try:
        result = subprocess.run(
            test_cmd, shell=True,
            capture_output=True, text=True,
            cwd=str(project_dir), timeout=300,
        )
        output = result.stdout[-3000:] + result.stderr[-2000:]
        passed = result.returncode == 0
        test_count = _parse_test_count(output)

        if passed:
            logger.info("EG4 test check passed (count=%s)", test_count)
        else:
            logger.warning("EG4 test check failed (exit code %d)", result.returncode)

        return TestCheckResult(
            passed=passed, test_count=test_count, output=output,
        )
    except subprocess.TimeoutExpired:
        logger.warning("EG4 test check timed out after 300s")
        return TestCheckResult(
            passed=False, output="Test check timed out after 300s",
        )
    except OSError as exc:
        logger.warning("EG4 test check error: %s", exc)
        return TestCheckResult(
            passed=False, output=f"Test check failed: {exc}",
        )


# ── Detection ────────────────────────────────────────────────────────────


def detect_test_cmd(
    project_dir: Path,
    override: str | None = None,
) -> str:
    """Auto-detect the test command for a project.

    Args:
        project_dir: Project root directory.
        override: Explicit command from config. ``"skip"`` disables.

    Returns:
        Command string, or empty string if nothing detected.
    """
    if override is not None:
        return "" if override == "skip" else override

    # ── Node.js ───────────────────────────────────────────────────
    pkg = project_dir / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            test_script = data.get("scripts", {}).get("test", "")
            if test_script and "no test specified" not in test_script:
                return "npm test"
        except (json.JSONDecodeError, OSError):
            pass

    # ── Python ────────────────────────────────────────────────────
    if (project_dir / "pytest.ini").exists():
        return "pytest"
    if (project_dir / "pyproject.toml").exists():
        try:
            text = (project_dir / "pyproject.toml").read_text()
            if "[tool.pytest" in text:
                return "pytest"
        except OSError:
            pass
    if (project_dir / "setup.cfg").exists():
        try:
            text = (project_dir / "setup.cfg").read_text()
            if "[tool:pytest]" in text:
                return "pytest"
        except OSError:
            pass
    # Fallback: pyproject.toml exists at all → assume pytest
    if (project_dir / "pyproject.toml").exists():
        return "pytest"

    # ── Rust ──────────────────────────────────────────────────────
    if (project_dir / "Cargo.toml").exists():
        return "cargo test"

    # ── Go ────────────────────────────────────────────────────────
    if (project_dir / "go.mod").exists():
        return "go test ./..."

    return ""
