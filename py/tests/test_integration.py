"""Integration tests for Auto-SDD V2 — step 6b.

Verify wiring between modules: BuildLoopV2, ExecGates (EG1–EG5),
local_agent, model_config. Each test uses real git repos, real
subprocess calls, real file I/O. Only run_local_agent is mocked
(no LLM in CI).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from auto_sdd.exec_gates.eg1_tool_calls import BuildAgentExecutor
from auto_sdd.exec_gates.eg3_build_check import check_build
from auto_sdd.exec_gates.eg4_test_check import check_tests
from auto_sdd.lib.local_agent import AgentResult, ToolCallBlocked, ToolCallRecord
from auto_sdd.lib.model_config import ModelConfig
from auto_sdd.scripts.build_loop_v2 import (
    BuildLoopV2,
    Feature,
    GateResult,
    _discover_test_files,
    _parse_roadmap,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _git(project: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a git command in the project dir."""
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(project),
        capture_output=True,
        text=True,
        timeout=10,
    )


def _cfg(**overrides: Any) -> ModelConfig:
    defaults = {
        "max_turns": 5,
        "timeout_seconds": 10,
        "strip_reasoning_older_turns": False,
    }
    defaults.update(overrides)
    return ModelConfig(**defaults)


def _agent_result(output: str = "", success: bool = True) -> AgentResult:
    """Build a canned AgentResult."""
    return AgentResult(
        output=output,
        finish_reason="stop" if success else "error",
        error="" if success else "agent failed",
        turn_count=3,
        duration_seconds=1.5,
    )


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def git_project(tmp_path: Path) -> Path:
    """Real git repo with roadmap, spec, test file, and initial commit."""
    # Init git
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@test.com")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "commit.gpgsign", "false")

    # package.json with build + test scripts
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"build": "echo build-ok", "test": "echo Tests: 2 passed"},
        "devDependencies": {"typescript": "5.0"},
    }))
    (tmp_path / "tsconfig.json").write_text("{}")

    # Roadmap with one pending feature
    specs = tmp_path / ".specs"
    specs.mkdir()
    (specs / "roadmap.md").write_text(
        "| ID | Name | Domain | Deps | Complexity | Notes | Status |\n"
        "|----|------|--------|------|------------|-------|--------|\n"
        "| 1 | Auth | core | - | S | - | ⬜ |\n"
    )

    # Feature spec
    feat_dir = specs / "features" / "core"
    feat_dir.mkdir(parents=True)
    (feat_dir / "auth.feature.md").write_text(
        "---\nfeature: Auth\ndomain: core\nstatus: pending\n---\n"
        "## Scenario: User logs in\n"
        "Given a registered user\nWhen they submit credentials\n"
        "Then they receive a token\n"
    )

    # A test file (to verify protected_paths discovery)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export const x = 1;\n")
    test_dir = tmp_path / "__tests__"
    test_dir.mkdir()
    (test_dir / "auth.test.ts").write_text("test('placeholder', () => {});\n")

    # Initial commit
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "initial")

    return tmp_path


@pytest.fixture
def git_project_two_features(git_project: Path) -> Path:
    """Extends git_project with a second feature depending on Auth."""
    roadmap = git_project / ".specs" / "roadmap.md"
    roadmap.write_text(
        "| ID | Name | Domain | Deps | Complexity | Notes | Status |\n"
        "|----|------|--------|------|------------|-------|--------|\n"
        "| 1 | Auth | core | - | S | - | ⬜ |\n"
        "| 2 | Dashboard | ui | Auth | M | - | ⬜ |\n"
    )
    feat_dir = git_project / ".specs" / "features" / "ui"
    feat_dir.mkdir(parents=True)
    (feat_dir / "dashboard.feature.md").write_text(
        "---\nfeature: Dashboard\ndomain: ui\nstatus: pending\n---\n"
        "## Scenario: User sees dashboard\n"
        "Given an authenticated user\nWhen they load the app\n"
        "Then they see the dashboard with widgets\n"
    )
    _git(git_project, "add", ".")
    _git(git_project, "commit", "-m", "add dashboard spec")
    return git_project


def _simulate_agent_build(
    project: Path,
    feature_name: str,
    source_file: str = "src/auth.ts",
    spec_file: str = "",
) -> AgentResult:
    """Simulate what a successful agent does: write file, commit, emit signals.

    Creates the file and git commit that the real agent would have made,
    then returns an AgentResult with matching signals.
    """
    src = project / source_file
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(f"// {feature_name} implementation\nexport function {feature_name.lower()}() {{}}\n")
    _git(project, "add", ".")
    _git(project, "commit", "-m", f"feat: {feature_name}")

    if not spec_file:
        spec_file = f".specs/features/core/{feature_name.lower()}.feature.md"
    return _agent_result(
        output=(
            f"I've implemented {feature_name}.\n"
            f"FEATURE_BUILT: {feature_name}\n"
            f"SPEC_FILE: {spec_file}\n"
            f"SOURCE_FILES: {source_file}\n"
        ),
    )


# ── BuildLoopV2 integration tests ───────────────────────────────────────────


class TestBuildLoopIntegration:
    """End-to-end BuildLoopV2 with mocked agent, real git, real subprocess."""

    PATCH_TARGET = "auto_sdd.scripts.build_loop_v2.run_local_agent"

    def test_single_feature_success(self, git_project: Path) -> None:
        """Agent succeeds → all gates pass → feature recorded as built."""

        def mock_agent(*_args, **_kwargs) -> AgentResult:
            return _simulate_agent_build(git_project, "Auth")

        with patch(self.PATCH_TARGET, side_effect=mock_agent):
            loop = BuildLoopV2(
                model_config=_cfg(),
                project_dir=git_project,
                build_cmd="echo build-ok",
                test_cmd='echo "Tests: 2 passed"',
                auto_approve=True,
            )
            exit_code = loop.run()

        assert exit_code == 0
        assert loop.built == 1
        assert loop.failed == 0
        assert len(loop.records) == 1
        assert loop.records[0].status == "built"
        assert loop.records[0].name == "Auth"

    def test_agent_failure_recorded(self, git_project: Path) -> None:
        """Agent returns error → feature recorded as failed."""
        fail_result = _agent_result(output="", success=False)

        with patch(self.PATCH_TARGET, return_value=fail_result):
            loop = BuildLoopV2(
                model_config=_cfg(),
                project_dir=git_project,
                build_cmd="echo ok",
                test_cmd='echo "Tests: 1 passed"',
                max_retries=0,
                auto_approve=True,
            )
            exit_code = loop.run()

        assert exit_code == 1
        assert loop.failed == 1
        assert loop.records[0].status == "failed"

    def test_gate_eg2_failure_missing_signals(self, git_project: Path) -> None:
        """Agent output has no signals → EG2 fails → feature failed."""
        # Agent "succeeds" (finish_reason=stop) but output has no signals
        no_signals = _agent_result(output="I did some work but forgot signals.\n")
        # Still need a commit for the agent to have "done something"
        (git_project / "src" / "junk.ts").write_text("// junk\n")
        _git(git_project, "add", ".")
        _git(git_project, "commit", "-m", "junk")

        with patch(self.PATCH_TARGET, return_value=no_signals):
            loop = BuildLoopV2(
                model_config=_cfg(),
                project_dir=git_project,
                build_cmd="echo ok",
                test_cmd='echo "Tests: 1 passed"',
                max_retries=0,
                auto_approve=True,
            )
            exit_code = loop.run()

        assert exit_code == 1
        assert loop.failed == 1
        assert "EG2" in loop.records[0].error

    def test_retry_attempt1_git_reset_then_success(self, git_project: Path) -> None:
        """Attempt 0 fails EG2, attempt 1 resets and succeeds."""
        head_before = _git(git_project, "rev-parse", "HEAD").stdout.strip()

        call_count = 0

        def mock_agent(*_args, **_kwargs) -> AgentResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First attempt: commit but no signals
                (git_project / "src" / "bad.ts").write_text("// bad\n")
                _git(git_project, "add", ".")
                _git(git_project, "commit", "-m", "bad attempt")
                return _agent_result(output="Oops, no signals.\n")
            else:
                # Second attempt (after git reset): proper build
                return _simulate_agent_build(git_project, "Auth")

        with patch(self.PATCH_TARGET, side_effect=mock_agent):
            loop = BuildLoopV2(
                model_config=_cfg(),
                project_dir=git_project,
                build_cmd="echo ok",
                test_cmd='echo "Tests: 2 passed"',
                max_retries=1,
                auto_approve=True,
            )
            exit_code = loop.run()

        assert exit_code == 0
        assert loop.built == 1
        assert call_count == 2

    def test_two_features_topo_order(self, git_project_two_features: Path) -> None:
        """Two features with dependency: Auth first, Dashboard second."""
        project = git_project_two_features
        call_order: list[str] = []

        def mock_agent(*_args, **kwargs) -> AgentResult:
            # Infer feature name from user_prompt content
            prompt = kwargs.get("user_prompt", "") or (_args[3] if len(_args) > 3 else "")
            if "Auth" in prompt:
                call_order.append("Auth")
                return _simulate_agent_build(project, "Auth", "src/auth.ts")
            else:
                call_order.append("Dashboard")
                return _simulate_agent_build(
                    project, "Dashboard", "src/dashboard.ts",
                    spec_file=".specs/features/ui/dashboard.feature.md",
                )

        with patch(self.PATCH_TARGET, side_effect=mock_agent):
            loop = BuildLoopV2(
                model_config=_cfg(),
                project_dir=project,
                build_cmd="echo ok",
                test_cmd='echo "Tests: 3 passed"',
                auto_approve=True,
            )
            loop.run()

        assert call_order == ["Auth", "Dashboard"]

    def test_summary_file_written(self, git_project: Path) -> None:
        """After run(), logs/build-summary-*.json exists with correct shape."""

        def mock_agent(*_args, **_kwargs) -> AgentResult:
            return _simulate_agent_build(git_project, "Auth")

        with patch(self.PATCH_TARGET, side_effect=mock_agent):
            loop = BuildLoopV2(
                model_config=_cfg(),
                project_dir=git_project,
                build_cmd="echo ok",
                test_cmd='echo "Tests: 2 passed"',
                auto_approve=True,
            )
            loop.run()

        logs = list((git_project / "logs").glob("build-summary-*.json"))
        assert len(logs) == 1
        summary = json.loads(logs[0].read_text())
        assert summary["built"] == 1
        assert summary["failed"] == 0
        assert len(summary["features"]) == 1
        assert summary["features"][0]["status"] == "built"

    def test_gate_eg3_build_failure(self, git_project: Path) -> None:
        """Build command fails → EG3 fails → feature failed."""
        agent_result = _simulate_agent_build(git_project, "Auth")

        with patch(self.PATCH_TARGET, return_value=agent_result):
            loop = BuildLoopV2(
                model_config=_cfg(),
                project_dir=git_project,
                build_cmd="exit 1",  # Build fails
                test_cmd='echo "Tests: 1 passed"',
                max_retries=0,
                auto_approve=True,
            )
            exit_code = loop.run()

        assert exit_code == 1
        assert "EG3" in loop.records[0].error

    def test_gate_eg4_test_failure(self, git_project: Path) -> None:
        """Test command fails → EG4 fails → feature failed."""
        agent_result = _simulate_agent_build(git_project, "Auth")

        with patch(self.PATCH_TARGET, return_value=agent_result):
            loop = BuildLoopV2(
                model_config=_cfg(),
                project_dir=git_project,
                build_cmd="echo ok",
                test_cmd="exit 1",  # Tests fail
                max_retries=0,
                auto_approve=True,
            )
            exit_code = loop.run()

        assert exit_code == 1
        assert "EG4" in loop.records[0].error

    def test_gate_eg5_head_not_advanced(self, git_project: Path) -> None:
        """Agent output has signals but no commit → EG5 fails."""
        # Don't commit anything — just emit signals pointing to existing files
        spec = git_project / ".specs" / "features" / "core" / "auth.feature.md"
        agent_result = _agent_result(
            output=(
                "FEATURE_BUILT: Auth\n"
                f"SPEC_FILE: {spec.relative_to(git_project)}\n"
                "SOURCE_FILES: src/index.ts\n"
            ),
        )

        with patch(self.PATCH_TARGET, return_value=agent_result):
            loop = BuildLoopV2(
                model_config=_cfg(),
                project_dir=git_project,
                build_cmd="echo ok",
                test_cmd='echo "Tests: 1 passed"',
                max_retries=0,
                auto_approve=True,
            )
            exit_code = loop.run()

        assert exit_code == 1
        assert "EG5" in loop.records[0].error


# ── Gate pipeline short-circuit tests ────────────────────────────────────────


class TestGatePipelineShortCircuit:
    """Verify _run_gate() short-circuits: failed check → later checks are None."""

    def test_all_pass(self, git_project: Path) -> None:
        """All gates pass → gate.passed is True, all result fields populated."""
        _simulate_agent_build(git_project, "Auth")
        head_before_build = _git(
            git_project, "rev-parse", "HEAD~1"
        ).stdout.strip()

        loop = BuildLoopV2(
            model_config=_cfg(),
            project_dir=git_project,
            build_cmd="echo ok",
            test_cmd='echo "Tests: 2 passed"',
            auto_approve=True,
        )
        agent_result = _agent_result(
            output=(
                "FEATURE_BUILT: Auth\n"
                "SPEC_FILE: .specs/features/core/auth.feature.md\n"
                "SOURCE_FILES: src/auth.ts\n"
            ),
        )
        gate = loop._run_gate(agent_result, head_before_build, 0)

        assert gate.passed is True
        assert gate.eg2_signals is not None
        assert gate.eg3_build is not None
        assert gate.eg4_tests is not None
        assert gate.eg5_commit is not None

    def test_eg2_fail_skips_eg3_eg4_eg5(self, git_project: Path) -> None:
        """EG2 failure → EG3/EG4/EG5 never run (are None)."""
        head = _git(git_project, "rev-parse", "HEAD").stdout.strip()
        loop = BuildLoopV2(
            model_config=_cfg(),
            project_dir=git_project,
            build_cmd="echo ok",
            test_cmd='echo "Tests: 1 passed"',
            auto_approve=True,
        )
        # No signals in output
        gate = loop._run_gate(_agent_result(output="no signals"), head, 0)

        assert gate.passed is False
        assert gate.failed_gate == "EG2"
        assert gate.eg2_signals is not None  # ran but failed
        assert gate.eg3_build is None
        assert gate.eg4_tests is None
        assert gate.eg5_commit is None

    def test_eg3_fail_skips_eg4_eg5(self, git_project: Path) -> None:
        """EG3 build failure → EG4/EG5 never run."""
        _simulate_agent_build(git_project, "Auth")
        head_before = _git(git_project, "rev-parse", "HEAD~1").stdout.strip()

        loop = BuildLoopV2(
            model_config=_cfg(),
            project_dir=git_project,
            build_cmd="exit 1",  # fails
            test_cmd='echo "Tests: 1 passed"',
            auto_approve=True,
        )
        agent_result = _agent_result(
            output=(
                "FEATURE_BUILT: Auth\n"
                "SPEC_FILE: .specs/features/core/auth.feature.md\n"
                "SOURCE_FILES: src/auth.ts\n"
            ),
        )
        gate = loop._run_gate(agent_result, head_before, 0)

        assert gate.failed_gate == "EG3"
        assert gate.eg2_signals is not None
        assert gate.eg3_build is not None  # ran but failed
        assert gate.eg4_tests is None
        assert gate.eg5_commit is None

    def test_eg4_fail_skips_eg5(self, git_project: Path) -> None:
        """EG4 test failure → EG5 never runs."""
        _simulate_agent_build(git_project, "Auth")
        head_before = _git(git_project, "rev-parse", "HEAD~1").stdout.strip()

        loop = BuildLoopV2(
            model_config=_cfg(),
            project_dir=git_project,
            build_cmd="echo ok",
            test_cmd="exit 1",  # tests fail
            auto_approve=True,
        )
        agent_result = _agent_result(
            output=(
                "FEATURE_BUILT: Auth\n"
                "SPEC_FILE: .specs/features/core/auth.feature.md\n"
                "SOURCE_FILES: src/auth.ts\n"
            ),
        )
        gate = loop._run_gate(agent_result, head_before, 0)

        assert gate.failed_gate == "EG4"
        assert gate.eg2_signals is not None
        assert gate.eg3_build is not None
        assert gate.eg4_tests is not None  # ran but failed
        assert gate.eg5_commit is None


# ── EG1 executor integration tests ──────────────────────────────────────────


class TestEG1ExecutorIntegration:
    """BuildAgentExecutor with real project dirs, real file I/O, real subprocess."""

    def test_write_read_command_cycle(self, git_project: Path) -> None:
        """Write a file, read it back, run a command — all through EG1."""
        executor = BuildAgentExecutor(
            project_root=git_project,
            command_timeout=10,
        )

        # Write
        w = json.loads(executor.execute("write_file", {
            "path": "src/new.ts",
            "content": "export const y = 2;\n",
        }))
        assert w["status"] == "success"
        assert (git_project / "src" / "new.ts").exists()

        # Read
        r = json.loads(executor.execute("read_file", {"path": "src/new.ts"}))
        assert "export const y = 2" in r["content"]

        # Command
        c = json.loads(executor.execute("run_command", {"command": "echo hello"}))
        assert c["returncode"] == 0
        assert "hello" in c["stdout"]

    def test_protected_paths_block_test_file_write(self, git_project: Path) -> None:
        """EG1 blocks writes to discovered test files."""
        test_cmd = 'echo "Tests: 1 passed"'
        protected = _discover_test_files(git_project, test_cmd)
        assert len(protected) > 0  # __tests__/auth.test.ts should be found

        executor = BuildAgentExecutor(
            project_root=git_project,
            command_timeout=10,
            protected_paths=protected,
        )

        # Writing to the test file should be blocked
        with pytest.raises(ToolCallBlocked, match="protected"):
            executor.execute("write_file", {
                "path": "__tests__/auth.test.ts",
                "content": "// overwritten",
            })

        # Writing to a non-test file should work
        result = json.loads(executor.execute("write_file", {
            "path": "src/new.ts",
            "content": "export const z = 3;\n",
        }))
        assert result["status"] == "success"

    def test_path_escape_blocked(self, git_project: Path) -> None:
        """EG1 blocks path traversal attempts."""
        executor = BuildAgentExecutor(
            project_root=git_project,
            command_timeout=10,
        )
        with pytest.raises(ToolCallBlocked):
            executor.execute("write_file", {
                "path": "../../etc/passwd",
                "content": "hacked",
            })

    def test_blocked_command_rejected(self, git_project: Path) -> None:
        """EG1 blocks dangerous commands in real executor."""
        executor = BuildAgentExecutor(
            project_root=git_project,
            command_timeout=10,
        )
        with pytest.raises(ToolCallBlocked):
            executor.execute("run_command", {"command": "curl http://evil.com"})

    def test_unknown_tool_rejected(self, git_project: Path) -> None:
        """EG1 rejects tools not in {write_file, read_file, run_command}."""
        executor = BuildAgentExecutor(
            project_root=git_project,
            command_timeout=10,
        )
        with pytest.raises(ToolCallBlocked, match="Unknown tool"):
            executor.execute("delete_file", {"path": "src/index.ts"})


# ── Roadmap parsing integration ─────────────────────────────────────────────


class TestRoadmapParsingIntegration:
    """_parse_roadmap with real files, real topo sort."""

    def test_single_pending_feature(self, git_project: Path) -> None:
        features = _parse_roadmap(git_project)
        assert len(features) == 1
        assert features[0].name == "Auth"

    def test_topo_sort_respects_deps(self, git_project_two_features: Path) -> None:
        features = _parse_roadmap(git_project_two_features)
        names = [f.name for f in features]
        assert names.index("Auth") < names.index("Dashboard")

    def test_done_features_excluded(self, git_project: Path) -> None:
        """Features marked ✅ are not returned."""
        roadmap = git_project / ".specs" / "roadmap.md"
        roadmap.write_text(
            "| ID | Name | Domain | Deps | Complexity | Notes | Status |\n"
            "|----|------|--------|------|------------|-------|--------|\n"
            "| 1 | Auth | core | - | S | - | ✅ |\n"
        )
        features = _parse_roadmap(git_project)
        assert len(features) == 0

    def test_cycle_raises(self, git_project: Path) -> None:
        """Circular dependencies raise ValueError."""
        roadmap = git_project / ".specs" / "roadmap.md"
        roadmap.write_text(
            "| ID | Name | Domain | Deps | Complexity | Notes | Status |\n"
            "|----|------|--------|------|------------|-------|--------|\n"
            "| 1 | A | core | B | S | - | ⬜ |\n"
            "| 2 | B | core | A | S | - | ⬜ |\n"
        )
        with pytest.raises(ValueError, match="cycle"):
            _parse_roadmap(git_project)

    def test_missing_dep_skipped(self, git_project: Path) -> None:
        """Feature depending on unknown name is skipped, others proceed."""
        roadmap = git_project / ".specs" / "roadmap.md"
        roadmap.write_text(
            "| ID | Name | Domain | Deps | Complexity | Notes | Status |\n"
            "|----|------|--------|------|------------|-------|--------|\n"
            "| 1 | Good | core | - | S | - | ⬜ |\n"
            "| 2 | Bad | core | NonExistent | S | - | ⬜ |\n"
        )
        features = _parse_roadmap(git_project)
        assert len(features) == 1
        assert features[0].name == "Good"


# ── Test file discovery integration ──────────────────────────────────────────


class TestDiscoverTestFiles:
    """_discover_test_files with real filesystem."""

    def test_discovers_jest_test(self, git_project: Path) -> None:
        """Finds __tests__/auth.test.ts in the git_project fixture."""
        found = _discover_test_files(git_project, 'echo "Tests: 1 passed"')
        assert any("auth.test.ts" in f for f in found)

    def test_discovers_pytest_files(self, tmp_path: Path) -> None:
        """Finds test_*.py files when pyproject.toml exists."""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_main.py").write_text("def test_one(): pass\n")
        (tmp_path / "tests" / "conftest.py").write_text("import pytest\n")

        found = _discover_test_files(tmp_path, "pytest")
        assert any("test_main.py" in f for f in found)
        assert any("conftest.py" in f for f in found)

    def test_ignores_node_modules(self, git_project: Path) -> None:
        """Test files inside node_modules are NOT protected."""
        nm = git_project / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "thing.test.js").write_text("test('x', () => {});\n")

        found = _discover_test_files(git_project, 'echo "Tests: 1 passed"')
        assert not any("node_modules" in f for f in found)


# ── EG2 signal parse + disk validation integration ───────────────────────────


class TestEG2DiskIntegration:
    """EG2 extract_and_validate with real files on disk."""

    def test_valid_signals_with_real_files(self, git_project: Path) -> None:
        """Signals pointing to real spec + source files pass."""
        from auto_sdd.exec_gates.eg2_signal_parse import extract_and_validate

        output = (
            "FEATURE_BUILT: Auth\n"
            "SPEC_FILE: .specs/features/core/auth.feature.md\n"
            "SOURCE_FILES: src/index.ts\n"
        )
        signals = extract_and_validate(output, git_project)
        assert signals.valid is True

    def test_source_file_missing_fails(self, git_project: Path) -> None:
        """SOURCE_FILES referencing nonexistent file fails."""
        from auto_sdd.exec_gates.eg2_signal_parse import extract_and_validate

        output = (
            "FEATURE_BUILT: Auth\n"
            "SPEC_FILE: .specs/features/core/auth.feature.md\n"
            "SOURCE_FILES: src/ghost.ts\n"
        )
        signals = extract_and_validate(output, git_project)
        assert signals.valid is False
        assert any(e.code == "SOURCE_MISSING" for e in signals.errors)

    def test_spec_outside_project_fails(self, git_project: Path) -> None:
        """SPEC_FILE resolving outside project_dir fails."""
        from auto_sdd.exec_gates.eg2_signal_parse import extract_and_validate

        output = (
            "FEATURE_BUILT: Auth\n"
            "SPEC_FILE: /etc/passwd\n"
            "SOURCE_FILES: src/index.ts\n"
        )
        signals = extract_and_validate(output, git_project)
        assert signals.valid is False


# ── EG3/EG4 subprocess integration ──────────────────────────────────────────


class TestEG3EG4SubprocessIntegration:
    """check_build / check_tests with real subprocess calls."""

    def test_build_pass(self, git_project: Path) -> None:
        result = check_build("echo build-ok", git_project)
        assert result.passed is True
        assert "build-ok" in result.output

    def test_build_fail(self, git_project: Path) -> None:
        result = check_build("exit 1", git_project)
        assert result.passed is False

    def test_build_skip(self, git_project: Path) -> None:
        result = check_build("", git_project)
        assert result.passed is True
        assert result.skipped is True

    def test_tests_pass_with_count(self, git_project: Path) -> None:
        result = check_tests('echo "Tests: 5 passed"', git_project)
        assert result.passed is True
        assert result.test_count == 5

    def test_tests_fail(self, git_project: Path) -> None:
        result = check_tests("exit 1", git_project)
        assert result.passed is False


# ── EG5 git state integration ───────────────────────────────────────────────


class TestEG5GitIntegration:
    """authorize_commit with real git repos."""

    def test_commit_authorized_after_real_commit(self, git_project: Path) -> None:
        """Real git commit → HEAD advances → authorized."""
        from auto_sdd.exec_gates.eg5_commit_auth import authorize_commit

        head_before = _git(git_project, "rev-parse", "HEAD").stdout.strip()

        (git_project / "src" / "new.ts").write_text("export const z = 1;\n")
        _git(git_project, "add", ".")
        _git(git_project, "commit", "-m", "feat: new")

        result = authorize_commit(
            project_dir=git_project,
            branch_start_commit=head_before,
            current_test_count=2,
            baseline_test_count=2,
        )
        assert result.authorized is True

    def test_no_commit_unauthorized(self, git_project: Path) -> None:
        """No commit made → HEAD same → unauthorized."""
        from auto_sdd.exec_gates.eg5_commit_auth import authorize_commit

        head = _git(git_project, "rev-parse", "HEAD").stdout.strip()

        result = authorize_commit(
            project_dir=git_project,
            branch_start_commit=head,
            current_test_count=1,
            baseline_test_count=1,
        )
        assert result.authorized is False
        assert any(e.code == "HEAD_UNCHANGED" for e in result.checks_failed)

    def test_test_regression_unauthorized(self, git_project: Path) -> None:
        """Test count drops below baseline → unauthorized."""
        from auto_sdd.exec_gates.eg5_commit_auth import authorize_commit

        head_before = _git(git_project, "rev-parse", "HEAD").stdout.strip()
        (git_project / "src" / "new.ts").write_text("export const z = 1;\n")
        _git(git_project, "add", ".")
        _git(git_project, "commit", "-m", "feat: new")

        result = authorize_commit(
            project_dir=git_project,
            branch_start_commit=head_before,
            current_test_count=1,
            baseline_test_count=5,
        )
        assert result.authorized is False
        assert any(e.code == "TEST_REGRESSION" for e in result.checks_failed)


# ── BuildLoopV2 config/limit tests ──────────────────────────────────────────


class TestBuildLoopConfig:
    """BuildLoopV2 constructor wiring and limits."""

    def test_max_features_limits_processing(self, git_project_two_features: Path) -> None:
        """max_features=1 processes only the first feature."""
        project = git_project_two_features

        def mock_agent(*_args, **_kwargs) -> AgentResult:
            return _simulate_agent_build(project, "Auth", "src/auth.ts")

        with patch("auto_sdd.scripts.build_loop_v2.run_local_agent", side_effect=mock_agent):
            loop = BuildLoopV2(
                model_config=_cfg(),
                project_dir=project,
                build_cmd="echo ok",
                test_cmd='echo "Tests: 2 passed"',
                max_features=1,
                auto_approve=True,
            )
            loop.run()

        assert loop.built == 1
        assert len(loop.records) == 1
        assert loop.records[0].name == "Auth"

    def test_auto_detect_build_test_cmd(self, git_project: Path) -> None:
        """BuildLoopV2 auto-detects build/test commands from package.json."""
        loop = BuildLoopV2(
            model_config=_cfg(),
            project_dir=git_project,
            auto_approve=True,
        )
        # tsconfig.json present → build should be tsc-based
        assert "tsc" in loop.build_cmd or "npx" in loop.build_cmd
        # package.json scripts.test = "jest" → test should be npm/jest-based
        assert "jest" in loop.test_cmd or "npm" in loop.test_cmd

    def test_explicit_cmd_overrides_detection(self, git_project: Path) -> None:
        """Explicit build/test commands override auto-detection."""
        loop = BuildLoopV2(
            model_config=_cfg(),
            project_dir=git_project,
            build_cmd="make build",
            test_cmd="make test",
            auto_approve=True,
        )
        assert loop.build_cmd == "make build"
        assert loop.test_cmd == "make test"

    def test_empty_roadmap_exits_clean(self, git_project: Path) -> None:
        """No pending features → run() returns 0 immediately."""
        roadmap = git_project / ".specs" / "roadmap.md"
        roadmap.write_text(
            "| ID | Name | Domain | Deps | Complexity | Notes | Status |\n"
            "|----|------|--------|------|------------|-------|--------|\n"
            "| 1 | Auth | core | - | S | - | ✅ |\n"
        )
        loop = BuildLoopV2(
            model_config=_cfg(),
            project_dir=git_project,
            build_cmd="echo ok",
            test_cmd="echo ok",
            auto_approve=True,
        )
        assert loop.run() == 0
        assert loop.built == 0
        assert loop.failed == 0
