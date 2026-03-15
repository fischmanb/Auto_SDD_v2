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
from auto_sdd.lib.reliability import (
    ResumeState, LockError,
    acquire_lock, release_lock,
    read_state, write_state, clean_state,
    new_campaign_id,
)
from auto_sdd.lib.branch_manager import (
    BranchError,
    setup_feature_branch, merge_feature_branch,
    delete_feature_branch, cleanup_merged_branches,
)
from auto_sdd.lib.codebase_summary import generate_codebase_summary
from auto_sdd.exec_gates.eg1_tool_calls import BuildAgentExecutor
from auto_sdd.exec_gates.eg2_signal_parse import extract_and_validate, ParsedSignals
from auto_sdd.exec_gates.eg3_build_check import check_build, detect_build_cmd, BuildCheckResult
from auto_sdd.exec_gates.eg4_test_check import check_tests, detect_test_cmd, TestCheckResult
from auto_sdd.exec_gates.eg5_commit_auth import authorize_commit, CommitAuthResult

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


@dataclass
class GateResult:
    """Aggregate result of all GATE checks (EG2–EG5).

    Checks run in order and short-circuit on first failure.
    Fields for checks that didn't run (due to short-circuit) stay None.

    EG2: Signal parse — agent emitted required signals, files exist
    EG3: Build check — project compiles
    EG4: Test check — all tests pass
    EG5: Commit auth — HEAD advanced, tree clean, no contamination, no regression
    EG6: Spec adherence — reserved, not yet implemented
    """

    passed: bool = False
    failed_gate: str = ""  # e.g., "EG2", "EG3", "EG4", "EG5"
    error: str = ""

    # Per-check results (None = didn't run due to short-circuit)
    eg2_signals: ParsedSignals | None = None
    eg3_build: BuildCheckResult | None = None
    eg4_tests: TestCheckResult | None = None
    eg5_commit: CommitAuthResult | None = None
    # eg6_spec_adherence: reserved


# ── Helpers ──────────────────────────────────────────────────────────────────


def _discover_test_files(project_dir: Path, test_cmd: str) -> set[str]:
    """Discover existing test files to protect from agent writes.

    Returns a set of paths relative to project_dir. These are passed
    to BuildAgentExecutor.protected_paths so the agent cannot modify,
    delete, or overwrite test files (enforced at EG1 layer).

    Discovery uses glob patterns based on the detected test framework.
    Only files that exist on disk at call time are returned.
    """
    patterns: list[str] = []

    # Pytest patterns
    if "pytest" in test_cmd or (project_dir / "pyproject.toml").exists():
        patterns += ["**/test_*.py", "**/*_test.py", "**/conftest.py"]

    # Jest / Vitest / Mocha patterns (JS/TS test ecosystem)
    if (project_dir / "package.json").exists():
        patterns += [
            "**/*.test.ts", "**/*.test.tsx",
            "**/*.test.js", "**/*.test.jsx",
            "**/*.spec.ts", "**/*.spec.tsx",
            "**/*.spec.js", "**/*.spec.jsx",
            "**/__tests__/**",
        ]

    found: set[str] = set()
    for pattern in patterns:
        for path in project_dir.glob(pattern):
            if path.is_file() and "node_modules" not in path.parts:
                found.add(str(path.relative_to(project_dir)))

    if found:
        logger.info("Protected test files: %d found", len(found))
    else:
        logger.warning("No test files discovered — nothing to protect")

    return found


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


def _parse_roadmap(project_dir: Path) -> list[Feature]:
    """Parse .specs/roadmap.md and return pending features in topo order.

    Uses shared table parser from validators, then filters pending features
    and topologically sorts by dependency.

    Returns ⬜ (pending) features topologically sorted by dependency.
    Features whose deps include names not in the roadmap (done or pending)
    are skipped with a warning. Cycles are detected and raise ValueError.
    """
    from auto_sdd.pre_build.validators import _parse_roadmap_table

    roadmap_path = project_dir / ".specs" / "roadmap.md"
    if not roadmap_path.exists():
        logger.error("Roadmap not found: %s", roadmap_path)
        return []

    text = roadmap_path.read_text()
    all_features, parse_errors = _parse_roadmap_table(text)

    if parse_errors:
        for err in parse_errors:
            logger.warning("Roadmap parse: %s: %s", err.code, err.detail)

    if not all_features:
        logger.warning("No parseable features in roadmap")
        return []

    # Separate pending vs done
    pending: dict[str, Feature] = {}
    done_names: set[str] = set()

    for name, data in all_features.items():
        if "✅" in data["status"]:
            done_names.add(name)
        elif "⬜" in data["status"]:
            pending[name] = Feature(
                id=data["id"],
                name=name,
                complexity=data["complexity"],
                deps=data["deps"],
                status="pending",
            )

    # ── Kahn's algorithm: topological sort with cycle detection ──
    # In-degree counts only pending→pending edges.
    # Deps that point to done_names are already satisfied.
    # Deps that point to unknown names (not done, not pending) → skip feature.
    in_degree: dict[str, int] = {name: 0 for name in pending}
    dependents: dict[str, list[str]] = {name: [] for name in pending}

    skipped_names: set[str] = set()
    for name, feat in pending.items():
        for dep in feat.deps:
            if dep in done_names:
                continue  # already satisfied
            if dep not in pending:
                logger.warning(
                    "Feature %r depends on %r which is not in roadmap — skipping",
                    name, dep,
                )
                skipped_names.add(name)
                break
            in_degree[name] += 1
            dependents[dep].append(name)

    # Cascade skips: if A is skipped and B depends on A, B must also skip.
    # Repeat until no new skips propagate.
    changed = True
    while changed:
        changed = False
        for name in list(pending.keys()):
            if name in skipped_names:
                continue
            for dep in pending[name].deps:
                if dep in skipped_names:
                    logger.warning(
                        "Feature %r depends on skipped %r — skipping",
                        name, dep,
                    )
                    skipped_names.add(name)
                    changed = True
                    break

    # Remove skipped features from the graph
    for name in skipped_names:
        in_degree.pop(name, None)
        dependents.pop(name, None)
    # Clean edges pointing to skipped features
    for name in list(in_degree.keys()):
        for dep in pending[name].deps:
            if dep in skipped_names:
                in_degree[name] = max(0, in_degree[name] - 1)

    # Seed queue with features that have zero in-degree
    from collections import deque
    queue: deque[str] = deque(
        name for name, deg in in_degree.items() if deg == 0
    )
    ordered: list[Feature] = []

    while queue:
        name = queue.popleft()
        ordered.append(pending[name])
        for dependent in dependents.get(name, []):
            if dependent in in_degree:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

    # Cycle detection: if we didn't process all features, there's a cycle
    remaining = {
        name for name, deg in in_degree.items()
        if deg > 0 and name not in skipped_names
    }
    if remaining:
        raise ValueError(
            f"Dependency cycle detected in roadmap among: "
            f"{', '.join(sorted(remaining))}"
        )

    logger.info(
        "Roadmap: %d pending, %d buildable (topo-sorted), %d done, %d skipped",
        len(pending), len(ordered), len(done_names), len(skipped_names),
    )
    return ordered


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


def _build_user_prompt(
    feature: Feature, project_dir: Path, codebase_summary: str = "",
) -> str:
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

    parts = [
        f"Implement the following feature:\n\n"
        f"Feature: {feature.name}\n"
        f"Complexity: {feature.complexity}\n\n"
        f"Specification:\n{spec_content}\n",
    ]

    if codebase_summary:
        parts.append(f"\n## Codebase Context\n\n{codebase_summary}\n")

    return "\n".join(parts)


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
        main_branch: str = "main",
        auto_approve: bool = False,
    ) -> None:
        self.config = model_config
        self.project_dir = project_dir.resolve()
        self.build_cmd = build_cmd or detect_build_cmd(self.project_dir)
        self.test_cmd = test_cmd or detect_test_cmd(self.project_dir)
        self.max_features = max_features
        self.max_retries = max_retries
        self.main_branch = main_branch
        self.auto_approve = auto_approve
        self._codebase_summary: str = ""

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

    # ── Entry point ──────────────────────────────────────────────────

    def run(self) -> int:
        """Execute the full build loop. Returns exit code.

        Acquires campaign lock, loads resume state, skips completed
        features, persists state after each success, cleans up on
        completion.
        """
        # ── Lock ─────────────────────────────────────────────────────
        try:
            acquire_lock(self.project_dir)
        except LockError as exc:
            logger.error("Cannot start: %s", exc)
            return 2

        try:
            return self._run_locked()
        finally:
            release_lock(self.project_dir)

    def _run_locked(self) -> int:
        """Inner run, called while holding the campaign lock."""
        features = _parse_roadmap(self.project_dir)
        if not features:
            logger.info("No buildable features found — nothing to do")
            return 0

        # ── Resume state ─────────────────────────────────────────────
        state = read_state(self.project_dir)
        if state is None:
            state = ResumeState(
                campaign_id=new_campaign_id(),
                started_at=datetime.now(timezone.utc).isoformat(),
            )

        # Filter out already-completed features
        completed_set = set(state.completed)
        if completed_set:
            before = len(features)
            features = [f for f in features if f.name not in completed_set]
            logger.info(
                "Resume: %d features skipped (%d remaining)",
                before - len(features), len(features),
            )

        if not features:
            logger.info("All features already completed — nothing to do")
            clean_state(self.project_dir)
            return 0

        limit = len(features)
        if self.max_features is not None:
            limit = min(limit, self.max_features)

        logger.info(
            "Starting build loop: %d features (limit %d), max retries %d",
            len(features), limit, self.max_retries,
        )

        # ── Codebase summary (generated once, reused per feature) ────
        self._codebase_summary = generate_codebase_summary(
            self.project_dir, self.config,
        )
        if self._codebase_summary:
            logger.info("Codebase summary: %d chars", len(self._codebase_summary))
        else:
            logger.info("Codebase summary: empty (no cache, agent skipped or failed)")

        # ── Preflight summary ────────────────────────────────────────
        if not self._preflight(features[:limit]):
            logger.info("Preflight rejected — aborting")
            return 3

        start_time = int(time.time())

        # ── Per-feature loop ─────────────────────────────────────────
        for idx in range(limit):
            feature = features[idx]
            feature_start = int(time.time())

            logger.info(
                "═══ [%d/%d] Feature: %s (complexity: %s) ═══",
                idx + 1, limit, feature.name, feature.complexity,
            )

            # Track current feature in resume state
            state.current = feature.name
            write_state(self.project_dir, state)

            success = self._build_feature(feature)

            duration = int(time.time()) - feature_start
            if success:
                self.built += 1
                # Persist completed feature for crash recovery
                state.completed.append(feature.name)
                state.current = ""
                write_state(self.project_dir, state)
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

        # Post-campaign cleanup
        cleanup_merged_branches(self.project_dir, self.main_branch)

        # Clean resume state on full success (no failures)
        if self.failed == 0:
            clean_state(self.project_dir)

        return 1 if self.failed > 0 else 0

    # ── Preflight summary ────────────────────────────────────────────

    def _preflight(self, features: list[Feature]) -> bool:
        """Print preflight summary. Returns True to proceed, False to abort.

        When auto_approve is False (default), waits for user confirmation.
        """
        print("\n" + "═" * 60)
        print("  AUTO-SDD V2 — Preflight Summary")
        print("═" * 60)
        print(f"  Model:    {self.config.model}")
        print(f"  Project:  {self.project_dir}")
        print(f"  Branch:   {self.main_branch}")
        print(f"  Build:    {self.build_cmd or '(none)'}")
        print(f"  Test:     {self.test_cmd or '(none)'}")
        print(f"  Retries:  {self.max_retries}")
        print(f"  Summary:  {'yes' if self._codebase_summary else 'no'}")
        print()
        print(f"  Features ({len(features)}):")
        for i, f in enumerate(features, 1):
            deps = f", deps={f.deps}" if f.deps else ""
            print(f"    {i}. {f.name} [{f.complexity}]{deps}")
        print()
        print("═" * 60)

        if self.auto_approve:
            print("  Auto-approved.\n")
            return True

        try:
            answer = input("  Proceed? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False

        return answer in ("y", "yes")

    # ── SELECT + BUILD + GATE + ADVANCE (per feature) ────────────────

    def _build_feature(self, feature: Feature) -> bool:
        """Build a single feature through the four-step pipeline.

        SELECT → BUILD → GATE → ADVANCE

        Creates a feature branch before the retry loop. On success,
        merges to main. On failure, deletes the branch.

        Returns True on success, False on failure after retries.
        """
        # ── Branch setup (once per feature) ──────────────────────
        try:
            branch_result = setup_feature_branch(
                self.project_dir, self.main_branch,
            )
        except BranchError as exc:
            logger.error("Branch setup failed for %s: %s", feature.name, exc)
            self._record(feature, "failed", 0, error=str(exc))
            return False

        branch_name = branch_result.branch_name

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                logger.info(
                    "Retry %d/%d for %s",
                    attempt, self.max_retries, feature.name,
                )

            # ── SELECT ───────────────────────────────────────────────
            # Capture baseline state before agent runs
            head_before = _get_head(self.project_dir)
            baseline_test_result = check_tests(
                self.test_cmd, self.project_dir,
            )
            baseline_test_count = baseline_test_result.test_count

            # Build prompts
            system_prompt = _build_system_prompt(feature, self.project_dir)
            user_prompt = _build_user_prompt(
                feature, self.project_dir, self._codebase_summary,
            )

            # Create executor (EG1 gate) scoped to this feature
            protected = _discover_test_files(self.project_dir, self.test_cmd)
            executor = BuildAgentExecutor(
                project_root=self.project_dir,
                allowed_branch=branch_name,
                command_timeout=60,
                protected_paths=protected,
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
                    if attempt >= 1:
                        self._git_reset(head_before)
                    continue
                delete_feature_branch(
                    self.project_dir, branch_name, self.main_branch,
                )
                return False

            # ── GATE (EG2 → EG3 → EG4 → EG5) ───────────────────────
            # All checks deterministic, orchestrator-side, short-circuit
            gate = self._run_gate(
                agent_result=agent_result,
                head_before=head_before,
                baseline_test_count=baseline_test_count,
            )

            if not gate.passed:
                logger.warning(
                    "GATE FAILED at %s: %s", gate.failed_gate, gate.error,
                )
                self._record(feature, "failed", attempt,
                             error=f"{gate.failed_gate}: {gate.error}")
                if attempt < self.max_retries:
                    if attempt >= 1:
                        self._git_reset(head_before)
                    continue
                delete_feature_branch(
                    self.project_dir, branch_name, self.main_branch,
                )
                return False

            # ── ADVANCE ──────────────────────────────────────────────
            # All gates passed — merge to main and record success
            current_test_count = (
                gate.eg4_tests.test_count if gate.eg4_tests else None
            )
            try:
                merge_feature_branch(
                    self.project_dir, branch_name, self.main_branch,
                )
            except BranchError as exc:
                logger.error("Merge failed for %s: %s", feature.name, exc)
                self._record(feature, "failed", attempt, error=str(exc))
                delete_feature_branch(
                    self.project_dir, branch_name, self.main_branch,
                )
                return False

            self._record(
                feature, "built", attempt,
                test_count=current_test_count,
            )
            return True

        # Exhausted all retries — clean up the feature branch
        delete_feature_branch(
            self.project_dir, branch_name, self.main_branch,
        )
        return False

    # ── GATE: deterministic ExecGate checks (EG2–EG5) ─────────────

    def _run_gate(
        self,
        agent_result: AgentResult,
        head_before: str,
        baseline_test_count: int | None,
    ) -> GateResult:
        """Run all GATE checks in sequence. Short-circuits on first failure.

        Execution order (AgentSpec lineage — all deterministic, agent-opaque):
            EG2: Signal parse — agent emitted required signals, files exist
            EG3: Build check — project compiles (orchestrator subprocess)
            EG4: Test check — all tests pass (orchestrator subprocess)
            EG5: Commit auth — HEAD advanced, tree clean, no contamination,
                 no test regression
            EG6: Spec adherence — reserved, not yet implemented

        Returns GateResult with per-check results. Fields for checks that
        didn't run (due to short-circuit) remain None.
        """
        gate = GateResult()

        # ── EG2: Signal parse ────────────────────────────────────
        signals = extract_and_validate(
            agent_result.output, self.project_dir,
        )
        gate.eg2_signals = signals

        if not signals.valid:
            gate.failed_gate = "EG2"
            gate.error = "; ".join(signals.errors)
            return gate

        logger.info(
            "EG2: signals valid (feature=%s, spec=%s, sources=%d)",
            signals.feature_name, signals.spec_file,
            len(signals.source_files),
        )

        # ── EG3: Build check ─────────────────────────────────────
        build_result = check_build(self.build_cmd, self.project_dir)
        gate.eg3_build = build_result

        if not build_result.passed:
            gate.failed_gate = "EG3"
            gate.error = f"Build failed: {build_result.output[-200:]}"
            return gate

        # ── EG4: Test check ──────────────────────────────────────
        test_result = check_tests(self.test_cmd, self.project_dir)
        gate.eg4_tests = test_result

        if not test_result.passed:
            gate.failed_gate = "EG4"
            gate.error = f"Tests failed: {test_result.output[-200:]}"
            return gate

        # ── EG5: Commit authorization ────────────────────────────
        commit_result = authorize_commit(
            project_dir=self.project_dir,
            branch_start_commit=head_before,
            current_test_count=test_result.test_count,
            baseline_test_count=baseline_test_count,
        )
        gate.eg5_commit = commit_result

        if not commit_result.authorized:
            gate.failed_gate = "EG5"
            gate.error = commit_result.summary
            return gate

        # ── EG6: Spec adherence (reserved) ───────────────────────
        # Not yet implemented. Will be deterministic diff-based
        # static analysis when added.

        # All checks passed
        gate.passed = True
        logger.info("GATE: all checks passed (%s)", commit_result.summary)
        return gate

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
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        default=bool(os.environ.get("AUTO_APPROVE", "")),
        help="Skip preflight confirmation (default: require approval)",
    )
    parser.add_argument(
        "--pre-build",
        action="store_true",
        default=False,
        help="Run pre-build phases (1-6) before the build loop",
    )
    parser.add_argument(
        "--vision-input",
        default=os.environ.get("VISION_INPUT", ""),
        help="User input for Phase 1 (VISION). Required if --pre-build and no .specs/vision.md",
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

    # Run pre-build phases if requested
    if args.pre_build:
        from auto_sdd.pre_build.orchestrator import run_pre_build

        logger.info("Running pre-build phases (1-6)...")
        pre_results = run_pre_build(
            config=config,
            project_dir=project_dir,
            user_input=args.vision_input,
        )
        failed = [r for r in pre_results if not r.passed]
        if failed:
            last = failed[-1]
            codes = [e.code for e in last.errors]
            logger.error(
                "Pre-build failed at %s: %s", last.phase, codes,
            )
            sys.exit(2)
        logger.info("Pre-build complete: %d phases passed", len(pre_results))

    # Run the loop
    loop = BuildLoopV2(
        model_config=config,
        project_dir=project_dir,
        build_cmd=args.build_cmd,
        test_cmd=args.test_cmd,
        max_features=args.max_features,
        max_retries=args.max_retries,
        auto_approve=args.auto_approve,
    )

    exit_code = loop.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
