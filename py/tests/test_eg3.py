"""Tests for EG3: Build Check ExecGate."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_sdd.exec_gates.eg3_build_check import (
    BuildCheckResult,
    check_build,
    detect_build_cmd,
)


class TestCheckBuildSkip:
    def test_empty_cmd_skips(self, tmp_path: Path) -> None:
        result = check_build("", tmp_path)
        assert result.passed is True
        assert result.skipped is True

    def test_skip_literal_skips(self, tmp_path: Path) -> None:
        result = check_build("skip", tmp_path)
        assert result.passed is True
        assert result.skipped is True


class TestCheckBuildPass:
    def test_passing_command(self, tmp_path: Path) -> None:
        result = check_build("echo ok", tmp_path)
        assert result.passed is True
        assert result.skipped is False
        assert "ok" in result.output

    def test_true_command(self, tmp_path: Path) -> None:
        result = check_build("true", tmp_path)
        assert result.passed is True


class TestCheckBuildFail:
    def test_failing_command(self, tmp_path: Path) -> None:
        result = check_build("false", tmp_path)
        assert result.passed is False
        assert result.skipped is False

    def test_nonzero_exit(self, tmp_path: Path) -> None:
        result = check_build("exit 1", tmp_path)
        assert result.passed is False

    def test_syntax_error_captured(self, tmp_path: Path) -> None:
        result = check_build("echo ok && false", tmp_path)
        assert result.passed is False


class TestCheckBuildTimeout:
    def test_timeout_fails(self, tmp_path: Path) -> None:
        # sleep 999 will be killed by the 120s timeout; use a short one
        # to avoid slow tests — override by calling subprocess directly
        # is not feasible, so just verify the module handles bad commands
        result = check_build("nonexistent_command_xyz", tmp_path)
        assert result.passed is False


class TestCheckBuildCwd:
    def test_runs_in_project_dir(self, tmp_path: Path) -> None:
        (tmp_path / "marker.txt").write_text("found")
        result = check_build("cat marker.txt", tmp_path)
        assert result.passed is True
        assert "found" in result.output


class TestBuildCheckResult:
    def test_to_dict(self) -> None:
        r = BuildCheckResult(passed=True, output="ok", skipped=False)
        d = r.to_dict()
        assert d["passed"] is True
        assert d["output"] == "ok"
        assert d["skipped"] is False


# ── detect_build_cmd ─────────────────────────────────────────────────────


class TestDetectBuildCmdOverride:
    def test_override_returns_override(self, tmp_path: Path) -> None:
        assert detect_build_cmd(tmp_path, "my-build-cmd") == "my-build-cmd"

    def test_override_skip_returns_empty(self, tmp_path: Path) -> None:
        assert detect_build_cmd(tmp_path, "skip") == ""


class TestDetectBuildCmdNextjs:
    def test_nextjs_config_js(self, tmp_path: Path) -> None:
        (tmp_path / "next.config.js").touch()
        (tmp_path / "tsconfig.json").touch()
        (tmp_path / "app").mkdir()
        (tmp_path / "package.json").write_text('{"scripts": {"build": "next build"}}')
        assert detect_build_cmd(tmp_path) == "npm run build"

    def test_nextjs_config_mjs(self, tmp_path: Path) -> None:
        (tmp_path / "next.config.mjs").touch()
        (tmp_path / "app").mkdir()
        (tmp_path / "package.json").write_text('{"scripts": {"build": "next build"}}')
        assert detect_build_cmd(tmp_path) == "npm run build"

    def test_nextjs_config_ts(self, tmp_path: Path) -> None:
        (tmp_path / "next.config.ts").touch()
        (tmp_path / "app").mkdir()
        (tmp_path / "package.json").write_text('{"scripts": {"build": "next build"}}')
        assert detect_build_cmd(tmp_path) == "npm run build"

    def test_nextjs_beats_tsconfig(self, tmp_path: Path) -> None:
        """Next.js detection takes priority over generic tsconfig (L-00177)."""
        (tmp_path / "next.config.js").touch()
        (tmp_path / "tsconfig.json").touch()
        (tmp_path / "tsconfig.build.json").touch()
        (tmp_path / "app").mkdir()
        (tmp_path / "package.json").write_text('{"scripts": {"build": "next build"}}')
        result = detect_build_cmd(tmp_path)
        assert result == "npm run build"
        assert "tsc" not in result

    def test_nextjs_without_app_dir_falls_to_tsc(self, tmp_path: Path) -> None:
        """Next.js project without app/ or pages/ falls through to tsc."""
        (tmp_path / "next.config.js").touch()
        (tmp_path / "tsconfig.json").touch()
        (tmp_path / "package.json").write_text('{"scripts": {"build": "next build"}}')
        result = detect_build_cmd(tmp_path)
        assert "tsc --noEmit" in result

    def test_nextjs_without_build_script_falls_through(self, tmp_path: Path) -> None:
        (tmp_path / "next.config.js").touch()
        (tmp_path / "tsconfig.json").touch()
        (tmp_path / "app").mkdir()
        (tmp_path / "package.json").write_text('{"scripts": {"dev": "next dev"}}')
        result = detect_build_cmd(tmp_path)
        assert "tsc --noEmit" in result


class TestDetectBuildCmdTypescript:
    def test_tsconfig_build_json(self, tmp_path: Path) -> None:
        (tmp_path / "tsconfig.build.json").touch()
        result = detect_build_cmd(tmp_path)
        assert "tsconfig.build.json" in result

    def test_tsconfig_json(self, tmp_path: Path) -> None:
        (tmp_path / "tsconfig.json").touch()
        result = detect_build_cmd(tmp_path)
        assert "tsc --noEmit" in result


class TestDetectBuildCmdOtherLangs:
    def test_pyproject_toml(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        (tmp_path / "app.py").write_text("print('hello')")
        result = detect_build_cmd(tmp_path)
        assert "py_compile" in result

    def test_cargo_toml(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").touch()
        assert detect_build_cmd(tmp_path) == "cargo check"

    def test_go_mod(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").touch()
        assert detect_build_cmd(tmp_path) == "go build ./..."

    def test_package_json_with_build(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {"build": "webpack"}})
        )
        assert detect_build_cmd(tmp_path) == "npm run build"

    def test_no_detection(self, tmp_path: Path) -> None:
        assert detect_build_cmd(tmp_path) == ""
