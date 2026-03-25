"""Tests for EG6: Spec Adherence ExecGate."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from auto_sdd.exec_gates.eg6_spec_adherence import (
    SpecAdherenceResult,
    _check_file_placement,
    _check_naming_convention,
    _check_source_match,
    _check_token_existence,
    _extract_directory_patterns,
    check_spec_adherence,
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


class TestCheckSourceMatch:
    def test_all_sources_in_diff(self) -> None:
        ok, err = _check_source_match(
            ["src/auth.ts", "src/login.ts"],
            {"src/auth.ts", "src/login.ts", "package.json"},
            Path("/project"),
        )
        assert ok is True
        assert err.code == "SOURCE_MATCH"

    def test_missing_source_in_diff(self) -> None:
        ok, err = _check_source_match(
            ["src/auth.ts", "src/ghost.ts"],
            {"src/auth.ts"},
            Path("/project"),
        )
        assert ok is False
        assert err.code == "SOURCE_NOT_IN_DIFF"
        assert "ghost.ts" in err.detail

    def test_empty_source_files(self) -> None:
        ok, err = _check_source_match([], {"src/auth.ts"}, Path("/project"))
        assert ok is True

    def test_extra_diff_files_ok(self) -> None:
        """Diff can contain more files than SOURCE_FILES (build artifacts etc.)."""
        ok, err = _check_source_match(
            ["src/auth.ts"],
            {"src/auth.ts", "node_modules/.cache/foo", "tsconfig.tsbuildinfo"},
            Path("/project"),
        )
        assert ok is True


class TestCheckFilePlacement:
    def test_files_in_expected_dirs(self, tmp_path: Path) -> None:
        specs = tmp_path / ".specs"
        specs.mkdir()
        (specs / "systems-design.md").write_text(
            "# Systems Design\n## Directory Structure\nsrc/ for source code\ntests/ for tests\n"
        )
        ok, err = _check_file_placement(["src/auth.ts", "tests/test_auth.py"], tmp_path)
        assert ok is True

    def test_file_in_unexpected_dir(self, tmp_path: Path) -> None:
        specs = tmp_path / ".specs"
        specs.mkdir()
        (specs / "systems-design.md").write_text(
            "# Systems Design\n## Directory Structure\nsrc/ for source code\n"
        )
        ok, err = _check_file_placement(["random_dir/auth.ts"], tmp_path)
        assert ok is False
        assert err.code == "FILE_MISPLACED"

    def test_hidden_dirs_always_allowed(self, tmp_path: Path) -> None:
        specs = tmp_path / ".specs"
        specs.mkdir()
        (specs / "systems-design.md").write_text(
            "# Systems Design\n## Directory Structure\nsrc/ only\n"
        )
        ok, err = _check_file_placement([".specs/features/auth.md"], tmp_path)
        assert ok is True

    def test_no_systems_design_skips(self, tmp_path: Path) -> None:
        ok, err = _check_file_placement(["anywhere/file.ts"], tmp_path)
        assert ok is True
        assert "skipped" in err.detail


class TestExtractDirectoryPatterns:
    def test_extracts_dirs(self) -> None:
        content = (
            "# Systems Design\n"
            "## Directory Structure\n"
            "- src/ for source code\n"
            "- tests/ for tests\n"
            "- scripts/ for build scripts\n"
            "## State Management\n"
            "React context\n"
        )
        dirs = _extract_directory_patterns(content)
        assert "src" in dirs
        assert "tests" in dirs
        assert "scripts" in dirs

    def test_always_includes_common_dirs(self) -> None:
        dirs = _extract_directory_patterns("# No directory section\n")
        assert "src" in dirs
        assert "tests" in dirs
        assert "lib" in dirs


class TestCheckTokenExistence:
    def test_valid_tokens(self, tmp_path: Path) -> None:
        ds = tmp_path / ".specs" / "design-system"
        ds.mkdir(parents=True)
        (ds / "tokens.md").write_text("# Tokens\n`emerald-500` `zinc-900`\n")
        src = tmp_path / "src"
        src.mkdir()
        (src / "App.tsx").write_text('export default () => <div className="bg-emerald-500">hi</div>')
        # emerald-500 is a standard Tailwind color, not a custom token
        ok, err = _check_token_existence(["src/App.tsx"], tmp_path)
        assert ok is True

    def test_no_tokens_file_skips(self, tmp_path: Path) -> None:
        ok, err = _check_token_existence(["src/App.tsx"], tmp_path)
        assert ok is True
        assert "skipped" in err.detail

    def test_non_ui_files_skipped(self, tmp_path: Path) -> None:
        ds = tmp_path / ".specs" / "design-system"
        ds.mkdir(parents=True)
        (ds / "tokens.md").write_text("# Tokens\n`emerald-500`\n")
        src = tmp_path / "src"
        src.mkdir()
        (src / "utils.py").write_text("# No token refs in python\n")
        ok, err = _check_token_existence(["src/utils.py"], tmp_path)
        assert ok is True


class TestCheckNamingConvention:
    def test_valid_react_component(self) -> None:
        ok, err = _check_naming_convention(
            ["src/components/AuthForm.tsx"], Path("/project"),
        )
        assert ok is True

    def test_invalid_react_component(self) -> None:
        ok, err = _check_naming_convention(
            ["src/components/auth-form.tsx"], Path("/project"),
        )
        assert ok is False
        assert err.code == "NAMING_VIOLATION"
        assert "PascalCase" in err.detail

    def test_valid_python_module(self) -> None:
        ok, err = _check_naming_convention(
            ["src/auth_handler.py"], Path("/project"),
        )
        assert ok is True

    def test_invalid_python_module(self) -> None:
        ok, err = _check_naming_convention(
            ["src/AuthHandler.py"], Path("/project"),
        )
        assert ok is False
        assert err.code == "NAMING_VIOLATION"

    def test_hooks_allowed_lowercase(self) -> None:
        """React hooks (useXxx) are allowed to start lowercase."""
        ok, err = _check_naming_convention(
            ["src/hooks/useAuth.tsx"], Path("/project"),
        )
        assert ok is True

    def test_hidden_files_skipped(self) -> None:
        ok, err = _check_naming_convention(
            [".eslintrc.js", "_internal.py"], Path("/project"),
        )
        assert ok is True


class TestCheckSpecAdherence:
    def test_all_pass(self, git_project: Path) -> None:
        start = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(git_project),
        ).stdout.strip()
        (git_project / "src").mkdir()
        (git_project / "src" / "Auth.tsx").write_text("export default function Auth() {}")
        _git(["add", "."], git_project)
        _git(["commit", "-m", "feat"], git_project)
        result = check_spec_adherence(
            project_dir=git_project,
            source_files=["src/Auth.tsx"],
            base_commit=start,
        )
        assert result.passed is True
        assert len(result.checks_failed) == 0

    def test_source_mismatch_fails(self, git_project: Path) -> None:
        start = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(git_project),
        ).stdout.strip()
        (git_project / "src").mkdir()
        (git_project / "src" / "Auth.tsx").write_text("export default function Auth() {}")
        _git(["add", "."], git_project)
        _git(["commit", "-m", "feat"], git_project)
        result = check_spec_adherence(
            project_dir=git_project,
            source_files=["src/Auth.tsx", "src/Ghost.tsx"],
            base_commit=start,
        )
        assert result.passed is False
        assert any(e.code == "SOURCE_NOT_IN_DIFF" for e in result.checks_failed)

    def test_to_dict(self) -> None:
        from auto_sdd.lib.types import GateError
        r = SpecAdherenceResult(
            passed=False,
            checks_passed=[GateError("A", "ok")],
            checks_failed=[GateError("B", "bad")],
        )
        d = r.to_dict()
        assert d["passed"] is False
        assert d["checks_failed"][0]["code"] == "B"
        assert "summary" in d
