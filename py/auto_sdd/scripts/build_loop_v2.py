"""Simplified Build Loop V2 — SELECT → BUILD → GATE → ADVANCE

Stripped-down orchestration loop for local model execution with
deterministic ExecGate enforcement. Replaces the 2,400-line v1
build_loop.py with ~500 lines covering only the four-step core.

Architecture principles (docs/architecture-principles.md):
  P1: Agent's only output is committed code (tests run by orchestrator)
  P2: Agent cannot reach orchestrator (path-contained sandbox)
  P3: Deterministic gates replace probabilistic agent judgment
  P4: Agent proposes; gate disposes (9-layer validation)
  P5: Stack awareness derived from project markers
  P6: Extensions stripped, not commented

Usage:
    cd Auto_SDD_v2
    .venv/bin/python -m auto_sdd.scripts.build_loop_v2

Configuration:
    Model: config/models/gpt-oss-120b.yaml (or pass --model-config)
    Project: PROJECT_DIR env var or --project-dir
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from auto_sdd.lib.model_config import ModelConfig
from auto_sdd.lib.local_agent import AgentResult, run_local_agent
from auto_sdd.exec_gates.eg1_tool_calls import BuildAgentExecutor
from auto_sdd.exec_gates.eg2_signal_parse import extract_and_validate, ParsedSignals
from auto_sdd.exec_gates.eg3_commit_auth import authorize_commit, CommitAuthResult

logger = logging.getLogger(__name__)

# ── Tool definitions for the build agent ─────────────────────────────────────

BUILD_AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file at the given path, creating directories as needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to project root"},
                    "content": {"type": "string", "description": "Complete file content"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to project root"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command and return stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    },
]


# ── Data types ───────────────────────────────────────────────────────────────


@dataclass
class Feature:
    """A feature from the roadmap to be built."""

    id: int
    name: str
    complexity: str = "M"
    deps: list[str] = field(default_factory=list)
    status: str = "pending"  # pending | built | failed | skipped


@dataclass
class FeatureRecord:
    """Record of a completed feature build."""

    name: str
    status: str  # built | failed | skipped
    duration: int = 0
    attempt: int = 0
    error: str = ""
    test_count: int | None = None
    timestamp: str = ""


# ── Helpers ──────────────────────────────────────────────────────────────────


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


def _format_duration(seconds: int) -> str:
    """Format seconds as human-readable duration."""
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def _run_build_check(build_cmd: str, project_dir: Path) -> tuple[bool, str]:
    """Run the project build command (orchestrator-side, per P1).

    Returns (success, output).
    """
    if not build_cmd or build_cmd == "skip":
        return True, "(build check skipped)"

    try:
        result = subprocess.run(
            build_cmd, shell=True,
            capture_output=True, text=True,
            cwd=str(project_dir), timeout=120,
        )
        output = result.stdout[-2000:] + result.stderr[-2000:]
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Build check timed out after 120s"
    except OSError as exc:
        return False, f"Build check failed: {exc}"


def _run_test_check(test_cmd: str, project_dir: Path) -> tuple[bool, int | None, str]:
    """Run the project test command (orchestrator-side, per P1).

    Returns (success, test_count_or_none, output).
    """
    if not test_cmd or test_cmd == "skip":
        return True, None, "(test check skipped)"

    try:
        result = subprocess.run(
            test_cmd, shell=True,
            capture_output=True, text=True,
            cwd=str(project_dir), timeout=300,
        )
        output = result.stdout[-3000:] + result.stderr[-2000:]

        # Parse test count from common frameworks
        import re
        test_count = None
        # Jest/Vitest: "Tests: X passed"
        m = re.search(r'Tests:\s+(\d+)\s+passed', output)
        if m:
            test_count = int(m.group(1))
        # Pytest: "X passed"
        if test_count is None:
            m = re.search(r'(\d+)\s+passed', output)
            if m:
                test_count = int(m.group(1))

        return result.returncode == 0, test_count, output
    except subprocess.TimeoutExpired:
        return False, None, "Test check timed out after 300s"
    except OSError as exc:
        return False, None, f"Test check failed: {exc}"


def _parse_roadmap(project_dir: Path) -> list[Feature]:
    """Parse .specs/roadmap.md and return pending features in topo order.

    Expects markdown table rows with format:
        | ID | Name | Domain | Deps | Complexity | Notes | Status |

    Status column: ⬜ = pending, ✅ = done, 🔄 = in progress, ⏸️ = blocked

    Returns only ⬜ (pending) features whose dependencies are all ✅.
    """
    roadmap_path = project_dir / ".specs" / "roadmap.md"
    if not roadmap_path.exists():
        logger.error("Roadmap not found: %s", roadmap_path)
        return []

    text = roadmap_path.read_text()
    features: list[Feature] = []
    done_names: set[str] = set()

    import re
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c]  # Remove empty from leading/trailing |
        if len(cells) < 7:
            continue

        # Skip header rows
        try:
            fid = int(cells[0])
        except (ValueError, IndexError):
            continue

        name = cells[1].strip()
        deps_str = cells[3].strip()
        complexity = cells[4].strip() or "M"
        status_cell = cells[6].strip()

        deps = [d.strip() for d in deps_str.split(",") if d.strip() and d.strip() != "-"]

        if "✅" in status_cell:
            done_names.add(name)
        elif "⬜" in status_cell:
            features.append(Feature(
                id=fid, name=name, complexity=complexity,
                deps=deps, status="pending",
            ))

    # Filter to features whose deps are all done
    buildable = [f for f in features if all(d in done_names for d in f.deps)]

    logger.info(
        "Roadmap: %d pending, %d buildable, %d done",
        len(features), len(buildable), len(done_names),
    )
    return buildable


# ── Build prompt construction ────────────────────────────────────────────────


def _build_system_prompt(feature: Feature, project_dir: Path) -> str:
    """Build the system prompt for the build agent.

    This is the minimal prompt that tells the agent what to do.
    Adapted from v1 prompt_builder.py but stripped to essentials.
    """
    return (
        "You are a build agent. You implement software features by writing "
        "code, running commands, and committing your work.\n\n"
        "RULES:\n"
        "- Call tools one at a time (no parallel calls)\n"
        "- Commit your work with git add + git commit when done\n"
        "- After committing, emit these signals on separate lines:\n"
        "    FEATURE_BUILT: <feature name>\n"
        "    SPEC_FILE: <path to the feature spec file>\n"
        "    SOURCE_FILES: <comma-separated list of files you created/modified>\n"
        "- Do NOT run tests — the orchestrator handles testing\n"
        "- Do NOT modify existing tests unless the feature spec requires it\n"
        "- Do NOT use git push, git merge, git rebase, or git checkout\n"
        f"\nProject root: {project_dir}\n"
    )


def _build_user_prompt(feature: Feature, project_dir: Path) -> str:
    """Build the user prompt with the feature spec and context."""
    spec_dir = project_dir / ".specs" / "features"
    spec_content = ""

    # Find the spec file for this feature
    if spec_dir.is_dir():
        for p in spec_dir.rglob("*.md"):
            if feature.name.lower().replace(" ", "-") in p.stem.lower():
                spec_content = p.read_text()
                break

    if not spec_content:
        spec_content = f"Implement the feature: {feature.name}"

    return (
        f"Implement the following feature:\n\n"
        f"Feature: {feature.name}\n"
        f"Complexity: {feature.complexity}\n\n"
        f"Specification:\n{spec_content}\n"
    )


# ── Core orchestrator ────────────────────────────────────────────────────────


class BuildLoopV2:
    """Simplified build loop: SELECT → BUILD → GATE → ADVANCE.

    Orchestrates local model execution with ExecGate enforcement.
    """

    def __init__(
        self,
        model_config: ModelConfig,
        project_dir: Path,
        build_cmd: str = "",
        test_cmd: str = "",
        max_features: int | None = None,
        max_retries: int = 1,
    ) -> None:
        self.config = model_config
        self.project_dir = project_dir.resolve()
        self.build_cmd = build_cmd or self._detect_build_cmd()
        self.test_cmd = test_cmd or self._detect_test_cmd()
        self.max_features = max_features
        self.max_retries = max_retries

        # Results tracking
        self.records: list[FeatureRecord] = []
        self.built: int = 0
        self.failed: int = 0
        self.skipped: int = 0

        logger.info(
            "BuildLoopV2 init: project=%s, model=%s, build=%s, test=%s",
            self.project_dir.name,
            self.config.model,
            self.build_cmd or "(none)",
            self.test_cmd or "(none)",
        )

    def _detect_build_cmd(self) -> str:
        """Auto-detect the build command from project files."""
        if (self.project_dir / "tsconfig.json").exists():
            return "npx tsc --noEmit"
        if (self.project_dir / "package.json").exists():
            try:
                pkg = json.loads((self.project_dir / "package.json").read_text())
                if "build" in pkg.get("scripts", {}):
                    return "npm run build"
            except (json.JSONDecodeError, OSError):
                pass
        return ""

    def _detect_test_cmd(self) -> str:
        """Auto-detect the test command from project files."""
        if (self.project_dir / "package.json").exists():
            try:
                pkg = json.loads((self.project_dir / "package.json").read_text())
                if "test" in pkg.get("scripts", {}):
                    return "npm test"
            except (json.JSONDecodeError, OSError):
                pass
        if (self.project_dir / "pyproject.toml").exists():
            return "pytest"
        return ""

    # ── Entry point ──────────────────────────────────────────────────

    def run(self) -> int:
        """Execute the full build loop. Returns exit code."""
        features = _parse_roadmap(self.project_dir)
        if not features:
            logger.info("No buildable features found — nothing to do")
            return 0

        limit = len(features)
        if self.max_features is not None:
            limit = min(limit, self.max_features)

        logger.info(
            "Starting build loop: %d features (limit %d), max retries %d",
            len(features), limit, self.max_retries,
        )

        start_time = int(time.time())

        # ── Per-feature loop ─────────────────────────────────────────
        for idx in range(limit):
            feature = features[idx]
            feature_start = int(time.time())

            logger.info(
                "═══ [%d/%d] Feature: %s (complexity: %s) ═══",
                idx + 1, limit, feature.name, feature.complexity,
            )

            success = self._build_feature(feature)

            duration = int(time.time()) - feature_start
            if success:
                self.built += 1
                logger.info(
                    "✓ %s built in %s", feature.name, _format_duration(duration),
                )
            else:
                self.failed += 1
                logger.warning(
                    "✗ %s failed after %s", feature.name, _format_duration(duration),
                )

        # ── Summary ──────────────────────────────────────────────────
        total_duration = int(time.time()) - start_time
        logger.info(
            "═══ Build loop complete: %d built, %d failed, %d skipped (%s) ═══",
            self.built, self.failed, self.skipped,
            _format_duration(total_duration),
        )

        self._write_summary(total_duration)
        return 1 if self.failed > 0 else 0

    # ── SELECT + BUILD + GATE + ADVANCE (per feature) ────────────────

    def _build_feature(self, feature: Feature) -> bool:
        """Build a single feature through the four-step pipeline.

        SELECT → BUILD → GATE → ADVANCE

        Returns True on success, False on failure after retries.
        """
        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                logger.info(
                    "Retry %d/%d for %s",
                    attempt, self.max_retries, feature.name,
                )

            # ── SELECT ───────────────────────────────────────────────
            # Capture baseline state before agent runs
            head_before = _get_head(self.project_dir)
            baseline_test_ok, baseline_test_count, _ = _run_test_check(
                self.test_cmd, self.project_dir,
            )

            # Build prompts
            system_prompt = _build_system_prompt(feature, self.project_dir)
            user_prompt = _build_user_prompt(feature, self.project_dir)

            # Create executor (EG1 gate) scoped to this feature
            executor = BuildAgentExecutor(
                project_root=self.project_dir,
                allowed_branch="",  # TODO: wire branch manager
                command_timeout=60,
            )

            logger.info("SELECT: prompt built, baseline captured (tests=%s)",
                        baseline_test_count)

            # ── BUILD ────────────────────────────────────────────────
            # Agent runs with EG1 intercepting every tool call
            logger.info("BUILD: invoking agent (%s)", self.config.model)

            agent_result: AgentResult = run_local_agent(
                config=self.config,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tools=BUILD_AGENT_TOOLS,
                executor=executor,
            )

            if not agent_result.success:
                logger.warning(
                    "BUILD failed: %s (turns=%d, reason=%s)",
                    agent_result.error,
                    agent_result.turn_count,
                    agent_result.finish_reason,
                )
                self._record(feature, "failed", attempt,
                             error=agent_result.error)
                if attempt < self.max_retries:
                    # Reset for retry — agent's uncommitted changes are
                    # left in place for attempt 1 (fix-in-place),
                    # git reset for attempt 2+ (clean retry)
                    if attempt >= 1:
                        self._git_reset(head_before)
                    continue
                return False

            # ── EG2: Signal parse ────────────────────────────────────
            # Mechanical extraction — no agent self-assessment accepted
            signals: ParsedSignals = extract_and_validate(
                agent_result.output, self.project_dir,
            )

            if not signals.valid:
                logger.warning(
                    "EG2 FAILED: %s", "; ".join(signals.errors),
                )
                self._record(feature, "failed", attempt,
                             error=f"EG2: {'; '.join(signals.errors)}")
                if attempt < self.max_retries:
                    if attempt >= 1:
                        self._git_reset(head_before)
                    continue
                return False

            logger.info(
                "EG2: signals valid (feature=%s, spec=%s, sources=%d)",
                signals.feature_name, signals.spec_file,
                len(signals.source_files),
            )

            # ── GATE: Mechanical checks (orchestrator-side, per P1) ──
            # Build check
            build_ok, build_output = _run_build_check(
                self.build_cmd, self.project_dir,
            )
            if not build_ok:
                logger.warning("GATE: build check failed")
                self._record(feature, "failed", attempt,
                             error=f"Build failed: {build_output[-200:]}")
                if attempt < self.max_retries:
                    if attempt >= 1:
                        self._git_reset(head_before)
                    continue
                return False

            # Test check (orchestrator runs tests, not agent)
            test_ok, current_test_count, test_output = _run_test_check(
                self.test_cmd, self.project_dir,
            )
            if not test_ok:
                logger.warning("GATE: test check failed")
                self._record(feature, "failed", attempt,
                             error=f"Tests failed: {test_output[-200:]}")
                if attempt < self.max_retries:
                    if attempt >= 1:
                        self._git_reset(head_before)
                    continue
                return False

            # ── EG3: Commit authorization ────────────────────────────
            # Final deterministic check before state advances
            commit_auth: CommitAuthResult = authorize_commit(
                project_dir=self.project_dir,
                branch_start_commit=head_before,
                current_test_count=current_test_count,
                baseline_test_count=baseline_test_count,
            )

            if not commit_auth.authorized:
                logger.warning("EG3 BLOCKED: %s", commit_auth.summary)
                self._record(feature, "failed", attempt,
                             error=f"EG3: {commit_auth.summary}")
                if attempt < self.max_retries:
                    if attempt >= 1:
                        self._git_reset(head_before)
                    continue
                return False

            logger.info("GATE: all checks passed (%s)", commit_auth.summary)

            # ── ADVANCE ──────────────────────────────────────────────
            # All gates passed — record success and move to next feature
            self._record(
                feature, "built", attempt,
                test_count=current_test_count,
            )
            return True

        # Exhausted all retries
        return False

    # ── Helper methods ───────────────────────────────────────────────

    def _record(
        self,
        feature: Feature,
        status: str,
        attempt: int,
        error: str = "",
        test_count: int | None = None,
    ) -> None:
        """Record a feature build result."""
        self.records.append(FeatureRecord(
            name=feature.name,
            status=status,
            attempt=attempt,
            error=error,
            test_count=test_count,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))

    def _git_reset(self, target_commit: str) -> None:
        """Reset the working tree to a specific commit for clean retry."""
        if not target_commit:
            return
        try:
            subprocess.run(
                ["git", "reset", "--hard", target_commit],
                cwd=str(self.project_dir),
                capture_output=True, timeout=30,
            )
            subprocess.run(
                ["git", "clean", "-fd"],
                cwd=str(self.project_dir),
                capture_output=True, timeout=30,
            )
            logger.info("Git reset to %s for clean retry", target_commit[:8])
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("Git reset failed: %s", exc)

    def _write_summary(self, total_duration: int) -> None:
        """Write build summary to logs/build-summary.json."""
        logs_dir = self.project_dir / "logs"
        logs_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        summary_path = logs_dir / f"build-summary-{timestamp}.json"

        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": self.config.model,
            "project": str(self.project_dir),
            "duration_seconds": total_duration,
            "duration_human": _format_duration(total_duration),
            "built": self.built,
            "failed": self.failed,
            "skipped": self.skipped,
            "total": self.built + self.failed + self.skipped,
            "features": [
                {
                    "name": r.name,
                    "status": r.status,
                    "attempt": r.attempt,
                    "test_count": r.test_count,
                    "error": r.error,
                    "timestamp": r.timestamp,
                }
                for r in self.records
            ],
        }

        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
        logger.info("Summary written to %s", summary_path)


# ── Entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point for the V2 build loop."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Auto-SDD V2: Simplified Build Loop",
    )
    parser.add_argument(
        "--model-config",
        default="config/models/gpt-oss-120b.yaml",
        help="Path to model YAML config file",
    )
    parser.add_argument(
        "--project-dir",
        default=os.environ.get("PROJECT_DIR", ""),
        help="Path to the target project (or set PROJECT_DIR env var)",
    )
    parser.add_argument(
        "--build-cmd",
        default=os.environ.get("BUILD_CHECK_CMD", ""),
        help="Build command (auto-detected if not set)",
    )
    parser.add_argument(
        "--test-cmd",
        default=os.environ.get("TEST_CHECK_CMD", ""),
        help="Test command (auto-detected if not set)",
    )
    parser.add_argument(
        "--max-features",
        type=int,
        default=int(os.environ.get("MAX_FEATURES", "0")) or None,
        help="Max features to build (default: all)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=int(os.environ.get("MAX_RETRIES", "1")),
        help="Max retries per feature (default: 1)",
    )
    args = parser.parse_args()

    # Validate project dir
    if not args.project_dir:
        parser.error("--project-dir is required (or set PROJECT_DIR env var)")

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        parser.error(f"Project directory does not exist: {project_dir}")

    # Load model config
    config_path = Path(args.model_config)
    if not config_path.exists():
        # Try relative to script location
        config_path = Path(__file__).resolve().parents[3] / args.model_config
    if not config_path.exists():
        parser.error(f"Model config not found: {args.model_config}")

    config = ModelConfig.from_yaml(config_path)

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Run the loop
    loop = BuildLoopV2(
        model_config=config,
        project_dir=project_dir,
        build_cmd=args.build_cmd,
        test_cmd=args.test_cmd,
        max_features=args.max_features,
        max_retries=args.max_retries,
    )

    exit_code = loop.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
