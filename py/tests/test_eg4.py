"""Tests for EG4: Test Check ExecGate."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_sdd.exec_gates.eg4_test_check import (
    TestCheckResult,
    _parse_test_count,
    check_tests,
    detect_test_cmd,
)


class TestParseTestCount:
    def test_jest_format(self) -> None:
        assert _parse_test_count("Tests: 42 passed") == 42

    def test_jest_format_no_colon(self) -> None:
        assert _parse_test_count("Tests 42 passed, 0 failed") == 42

    def test_vitest_format(self) -> None:
        assert _parse_test_count("Tests  42 passed | 0 failed") == 42

    def test_pytest_format(self) -> None:
        assert _parse_test_count("12 passed in 0.5s") == 12

    def test_pytest_with_warnings(self) -> None:
        assert _parse_test_count("===== 8 passed, 2 warnings in 1.2s =====") == 8

    def test_mocha_format(self) -> None:
        assert _parse_test_count("  15 passing (3s)") == 15

    def test_mocha_no_parens(self) -> None:
        assert _parse_test_count("  7 passing") == 7

    def test_cargo_test_format(self) -> None:
        assert _parse_test_count("test result: ok. 23 passed; 0 failed; 0 ignored") == 23

    def test_go_verbose(self) -> None:
        output = "--- PASS: TestFoo (0.00s)\n--- PASS: TestBar (0.01s)\n--- PASS: TestBaz (0.00s)"
        assert _parse_test_count(output) == 3

    def test_no_match(self) -> None:
        assert _parse_test_count("no test output here") is None

    def test_empty(self) -> None:
        assert _parse_test_count("") is None


class TestCheckTestsSkip:
    def test_empty_cmd_skips(self, tmp_path: Path) -> None:
        result = check_tests("", tmp_path)
        assert result.passed is True
        assert result.skipped is True

    def test_skip_literal_skips(self, tmp_path: Path) -> None:
        result = check_tests("skip", tmp_path)
        assert result.passed is True
        assert result.skipped is True


class TestCheckTestsPass:
    def test_passing_command(self, tmp_path: Path) -> None:
        result = check_tests("echo '5 passed in 0.1s'", tmp_path)
        assert result.passed is True
        assert result.test_count == 5
        assert result.skipped is False

    def test_zero_exit(self, tmp_path: Path) -> None:
        result = check_tests("true", tmp_path)
        assert result.passed is True
        assert result.test_count is None  # no parseable output


class TestCheckTestsFail:
    def test_failing_command(self, tmp_path: Path) -> None:
        result = check_tests("false", tmp_path)
        assert result.passed is False
        assert result.skipped is False

    def test_nonzero_exit(self, tmp_path: Path) -> None:
        result = check_tests("exit 1", tmp_path)
        assert result.passed is False


class TestCheckTestsCwd:
    def test_runs_in_project_dir(self, tmp_path: Path) -> None:
        (tmp_path / "marker.txt").write_text("found")
        result = check_tests("cat marker.txt && echo '3 passed'", tmp_path)
        assert result.passed is True
        assert result.test_count == 3


class TestTestCheckResult:
    def test_to_dict(self) -> None:
        r = TestCheckResult(passed=True, test_count=7, output="ok")
        d = r.to_dict()
        assert d["passed"] is True
        assert d["test_count"] == 7
        assert d["output"] == "ok"
        assert d["skipped"] is False


# ── detect_test_cmd ──────────────────────────────────────────────────────


class TestDetectTestCmdOverride:
    def test_override_returns_override(self, tmp_path: Path) -> None:
        assert detect_test_cmd(tmp_path, "my-test-cmd") == "my-test-cmd"

    def test_override_skip_returns_empty(self, tmp_path: Path) -> None:
        assert detect_test_cmd(tmp_path, "skip") == ""


class TestDetectTestCmdNode:
    def test_package_json_with_test(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest"}})
        )
        assert detect_test_cmd(tmp_path) == "npm test"

    def test_package_json_no_test_specified(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {"test": "echo \"Error: no test specified\" && exit 1"}})
        )
        assert detect_test_cmd(tmp_path) == ""

    def test_package_json_no_scripts(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(json.dumps({"name": "foo"}))
        assert detect_test_cmd(tmp_path) == ""


class TestDetectTestCmdPython:
    def test_pytest_ini(self, tmp_path: Path) -> None:
        (tmp_path / "pytest.ini").touch()
        assert detect_test_cmd(tmp_path) == "pytest"

    def test_pyproject_with_pytest_section(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
        assert detect_test_cmd(tmp_path) == "pytest"

    def test_setup_cfg_with_pytest(self, tmp_path: Path) -> None:
        (tmp_path / "setup.cfg").write_text("[tool:pytest]\n")
        assert detect_test_cmd(tmp_path) == "pytest"

    def test_pyproject_fallback(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\n")
        assert detect_test_cmd(tmp_path) == "pytest"


class TestDetectTestCmdOtherLangs:
    def test_cargo_toml(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").touch()
        assert detect_test_cmd(tmp_path) == "cargo test"

    def test_go_mod(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").touch()
        assert detect_test_cmd(tmp_path) == "go test ./..."

    def test_no_detection(self, tmp_path: Path) -> None:
        assert detect_test_cmd(tmp_path) == ""
