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
from auto_sdd.exec_gates.eg6_spec_adherence import check_spec_adherence, SpecAdherenceResult
from auto_sdd.lib.constants import BUILD_AGENT_TOOLS

logger = logging.getLogger(__name__)

# ── Optional KG integration (graceful degradation if unavailable) ─────────────
try:
    from auto_sdd_v2.knowledge_system.build_integration import (
        capture_reflection as _capture_reflection,
        detect_project_stack as _detect_project_stack,
        format_reflection_for_prompt as _format_reflection_for_prompt,
        inject_hardened_clues as _inject_hardened_clues,
        inject_knowledge_combined as _inject_knowledge_combined,
        inject_relevant_knowledge as _inject_relevant_knowledge,
        init_store_optional as _init_store_optional,
        kg_post_gate as _kg_post_gate_fn,
        reflect_on_failure as _reflect_on_failure,
        synthesize_universals as _synthesize_universals,
    )
    _KG_MODULE_AVAILABLE = True
except Exception:
    _KG_MODULE_AVAILABLE = False


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
    turn_count: int = 0
    tool_call_count: int = 0
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
    eg6_adherence: "SpecAdherenceResult | None" = None


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


def _get_diff(project_dir: Path, base_commit: str) -> str:
    """Get git diff between base_commit and HEAD (agent's changes).

    Returns the diff text (capped at 8000 chars to fit in prompt context),
    or empty string on error.
    """
    if not base_commit:
        return ""
    try:
        result = subprocess.run(
            ["git", "diff", base_commit, "HEAD", "--stat"],
            capture_output=True, text=True,
            cwd=str(project_dir), timeout=15,
        )
        stat = result.stdout.strip() if result.returncode == 0 else ""

        result = subprocess.run(
            ["git", "diff", base_commit, "HEAD"],
            capture_output=True, text=True,
            cwd=str(project_dir), timeout=30,
        )
        full = result.stdout.strip() if result.returncode == 0 else ""

        if not stat and not full:
            return ""

        # Stat summary always fits; cap the full diff to leave room in prompt
        diff = f"### File summary\n{stat}\n\n### Full diff\n{full}"
        if len(diff) > 8000:
            diff = diff[:8000] + "\n... (diff truncated)"
        return diff
    except (subprocess.TimeoutExpired, OSError):
        return ""


def _smart_truncate(text: str, max_len: int) -> str:
    """Truncate text keeping both start and end for context.

    If the text exceeds max_len, keeps the first 60% and last 40%
    with an elision marker in the middle. This preserves the error
    summary (usually at the start) and the specific failure details
    (usually at the end).
    """
    if len(text) <= max_len:
        return text
    head = int(max_len * 0.6)
    tail = max_len - head - 30  # 30 chars for marker
    return f"{text[:head]}\n\n... ({len(text) - max_len} chars elided) ...\n\n{text[-tail:]}"


def _extract_error_codes(gate: "GateResult") -> list[str]:
    """Extract structured error codes from a failed GateResult."""
    codes: list[str] = []
    if gate.failed_gate == "EG2" and gate.eg2_signals:
        codes = [e.code for e in gate.eg2_signals.errors]
    elif gate.failed_gate == "EG5" and gate.eg5_commit:
        codes = [e.code for e in gate.eg5_commit.checks_failed]
    elif gate.failed_gate == "EG6" and gate.eg6_adherence:
        codes = [e.code for e in gate.eg6_adherence.checks_failed]
    # EG3/EG4 don't have structured codes yet — gate name is enough
    return codes


# ── Retry guidance by failure type ────────────────────────────────────────

_RETRY_GUIDANCE: dict[str, str] = {
    # EG2 signal errors
    "MISSING_FEATURE_BUILT": (
        "You forgot to emit the FEATURE_BUILT signal. After committing, "
        "print: FEATURE_BUILT: <feature name>"
    ),
    "FEATURE_NAME_MISMATCH": (
        "Your FEATURE_BUILT signal doesn't match the feature you were asked "
        "to build. Emit: FEATURE_BUILT: <exact feature name from the spec>"
    ),
    "MISSING_SPEC_FILE": (
        "You forgot to emit the SPEC_FILE signal. After committing, "
        "print: SPEC_FILE: <path to spec>"
    ),
    "SOURCE_MISSING": (
        "One or more SOURCE_FILES you declared don't exist on disk. "
        "Either create the missing files or fix the SOURCE_FILES signal "
        "to list only files you actually created."
    ),
    "SPEC_NOT_FOUND": (
        "The SPEC_FILE you referenced doesn't exist. Check the path and "
        "make sure you're pointing to the actual spec file in .specs/."
    ),
    "SPEC_TOO_SHORT": (
        "The spec file has too little content (<25 chars). This is a "
        "pre-build issue — write a substantive spec before building."
    ),
    # EG6 spec adherence errors
    "SOURCE_NOT_IN_DIFF": (
        "Your SOURCE_FILES signal lists files that weren't actually "
        "changed. Update the signal to match only the files you modified."
    ),
    "FILE_MISPLACED": (
        "You created files in unexpected directories. Check the project's "
        "systems-design.md for the expected directory structure."
    ),
    "TOKEN_UNKNOWN": (
        "You referenced design tokens that don't exist in tokens.md. "
        "Use only tokens defined in .specs/design-system/tokens.md."
    ),
    "NAMING_VIOLATION": (
        "File names don't follow conventions: React components should be "
        "PascalCase (.tsx), Python modules should be snake_case (.py)."
    ),
    # EG5 commit errors
    "HEAD_UNCHANGED": (
        "You didn't commit your changes. Use git add and git commit "
        "before emitting signals."
    ),
    "TREE_DIRTY": (
        "You left uncommitted changes. Run git add for all modified files "
        "and commit them before emitting signals."
    ),
    "TEST_REGRESSION": (
        "Your changes caused existing tests to fail. Review the test "
        "output, identify which tests broke, and fix your implementation "
        "to preserve existing behavior."
    ),
}

# Gate-level fallback guidance when no specific error codes match
_GATE_GUIDANCE: dict[str, str] = {
    "BUILD": (
        "The agent crashed or timed out. Simplify your approach — "
        "implement the minimum viable version first."
    ),
    "EG2": (
        "Signal validation failed. After implementing and committing, "
        "emit FEATURE_BUILT, SPEC_FILE, and SOURCE_FILES signals."
    ),
    "EG3": (
        "The project failed to compile. Check for syntax errors, missing "
        "imports, and type errors in the files you wrote. Do NOT introduce "
        "new dependencies unless the spec requires them."
    ),
    "EG4": (
        "Tests failed. Read the test output carefully. Fix your "
        "implementation to make tests pass — do NOT modify existing tests "
        "unless the feature spec requires it."
    ),
    "EG5": (
        "Commit authorization failed. Make sure you commit all changes "
        "and don't modify files outside the project scope."
    ),
    "EG6": (
        "Spec adherence check failed. Your code doesn't match the "
        "structural requirements: check file placement, naming conventions, "
        "design token references, and that SOURCE_FILES matches what you "
        "actually changed."
    ),
}


def _retry_guidance(failed_gate: str, error_codes: list[str]) -> str:
    """Build targeted retry instructions based on failure type."""
    parts: list[str] = []

    # Specific guidance per error code
    for code in error_codes:
        if code in _RETRY_GUIDANCE:
            parts.append(f"- {_RETRY_GUIDANCE[code]}")

    # Gate-level fallback if no specific codes matched
    if not parts and failed_gate in _GATE_GUIDANCE:
        parts.append(_GATE_GUIDANCE[failed_gate])

    if parts:
        guidance = "## RETRY STRATEGY\n" + "\n".join(parts) + "\n\n"
    else:
        guidance = ""

    # Always include the general instruction
    guidance += (
        "Fix ONLY the errors above. The import signatures for all "
        "existing modules are already provided in this prompt. Do "
        "NOT re-read files whose exports are listed above. Read "
        "ONLY your own files if you need to see what you wrote, "
        "then write corrected versions immediately.\n"
    )
    return guidance


def _format_duration(seconds: int) -> str:
    """Format seconds as human-readable duration."""
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def _status(msg: str) -> None:
    """Print a prominent status message with visual separation."""
    print(f"\n\n  {msg}\n\n", flush=True)


def _turns_for_complexity(complexity: str, base_turns: int) -> int:
    """Scale max_turns based on feature complexity.

    S features get the base config value. M features get 1.5x. L+ get 2x.
    """
    c = complexity.upper().split()[0] if complexity else "M"
    if c == "S":
        return base_turns
    if c == "L" or c == "XL":
        return int(base_turns * 2)
    return int(base_turns * 1.5)


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

    # ── Normalize dep names (P8: fixes must generalize) ──
    # Models write dep names that don't exactly match feature names.
    # Resolution order:
    #   1. Exact match
    #   2. Normalized match (strip non-alnum, lowercase)
    #   3. Token subset match (all dep words appear in feature name)
    # This handles "Global Layout" → "Global Layout & Theming",
    # "data-loader" → "Data Loader", etc.
    import re as _re

    def _normalize(s: str) -> str:
        return "".join(c for c in s.lower() if c.isalnum())

    def _tokens(s: str) -> set[str]:
        return set(_re.findall(r"[a-z0-9]+", s.lower()))

    all_names = set(pending.keys()) | done_names
    norm_to_name: dict[str, str] = {_normalize(n): n for n in all_names}

    def _resolve_dep(dep: str) -> str:
        """Resolve a dep name to an actual feature name."""
        if dep in all_names:
            return dep
        # Try normalized exact match
        norm_dep = _normalize(dep)
        match = norm_to_name.get(norm_dep)
        if match:
            return match
        # Try token subset: all dep tokens present in a feature name
        dep_tokens = _tokens(dep)
        if dep_tokens:
            candidates = [
                n for n in all_names
                if dep_tokens <= _tokens(n)
            ]
            if len(candidates) == 1:
                return candidates[0]
        return dep  # unresolved, will be caught below

    for name, feat in pending.items():
        resolved_deps: list[str] = []
        for dep in feat.deps:
            resolved = _resolve_dep(dep)
            if resolved != dep:
                logger.info(
                    "Dep %r resolved to %r (fuzzy match)", dep, resolved,
                )
            resolved_deps.append(resolved)
        feat.deps = resolved_deps

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


def _scan_dep_exports(project_dir: Path) -> str:
    """Scan existing source files and extract export signatures.

    Returns a formatted string showing each file's path and its exports.
    This gives the build agent exact knowledge of what's importable
    without burning turns reading every file.
    """
    import re

    src_dir = project_dir / "src"
    if not src_dir.is_dir():
        return ""

    lines: list[str] = []
    for ext in ("*.ts", "*.tsx"):
        for fpath in sorted(src_dir.rglob(ext)):
            rel = str(fpath.relative_to(project_dir))
            if "__tests__" in rel or ".test." in rel:
                continue
            try:
                content = fpath.read_text(errors="replace")
            except OSError:
                continue
            exports = []
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("export "):
                    # Trim to first { or ( for readability
                    sig = stripped[:120]
                    exports.append(sig)
            if exports:
                lines.append(f"\n### {rel}")
                for e in exports[:15]:
                    lines.append(f"  {e}")

    if not lines:
        return ""

    return "## Available Imports (already built)\n" + "\n".join(lines) + "\n"


def _build_system_prompt(
    feature: Feature,
    project_dir: Path,
    blocked_patterns: list[str] | None = None,
    *,
    kg_clues: str = "",
) -> str:
    """Build the system prompt for the build agent.

    This is the minimal prompt that tells the agent what to do.
    Adapted from v1 prompt_builder.py but stripped to essentials.
    """
    prompt = (
        "You are a build agent. You implement software features using three tools: "
        "write_file, read_file, and run_command.\n\n"
        "TOOLS:\n"
        "- read_file(path): Read any file. This is how you read files. Do NOT use "
        "run_command with cat, sed, head, tail, or python to read files.\n"
        "- write_file(path, content): Create or overwrite a file.\n"
        "- run_command(command): Run shell commands. Only use for: git add, git commit, "
        "npm install, npm run, npx, and project build/test commands. Do NOT use for "
        "reading files or general scripting.\n\n"
        "RULES:\n"
        "- Call tools one at a time (no parallel calls)\n"
        "- Read the feature spec and existing code with read_file before writing\n"
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

    if blocked_patterns:
        # Deduplicate and cap at 10 most recent
        seen: set[str] = set()
        unique: list[str] = []
        for p in reversed(blocked_patterns):
            if p not in seen:
                seen.add(p)
                unique.append(p)
            if len(unique) >= 10:
                break
        unique.reverse()

        prompt += (
            "\nIMPORTANT — these tool calls were rejected in previous builds. "
            "Do NOT repeat them:\n"
        )
        for p in unique:
            prompt += f"- {p}\n"

    if kg_clues:
        prompt += kg_clues

    return prompt


def _is_ui_feature(spec_content: str) -> bool:
    """Heuristic: does this feature spec describe UI work?

    Returns True if the spec references design tokens, UI components,
    or visual elements — meaning design patterns are relevant context.
    """
    import re
    lower = spec_content.lower()

    # Backtick-wrapped token references like `emerald-500`, `p-4`
    if re.search(r"`[a-z]+-[a-z0-9]+(?:-[a-z0-9]+)*`", spec_content):
        return True

    # Explicit UI signals in the spec text.
    # Avoid ambiguous words like "table" (could be DB table) or "input"
    # (could be CLI input) — use compound phrases for those.
    ui_keywords = (
        "design token", "component", "layout", "render", "button",
        "modal", "form field", "card", "sidebar", "navbar", "dashboard",
        "chart", "data table", "dialog", "tooltip", "dropdown",
        "checkbox", "toggle", "tabs", "panel", "grid layout", "flexbox",
        ".tsx", ".jsx", "classname", "tailwind", "css",
        "ui ", " ui", "user interface",
    )
    return any(kw in lower for kw in ui_keywords)


def _read_arch_summary(project_dir: Path) -> str:
    """Read vision.md and systems-design.md into a brief architecture context.

    Caps total at 1500 chars to avoid bloating the prompt.
    """
    parts: list[str] = []
    vision_path = project_dir / ".specs" / "vision.md"
    systems_path = project_dir / ".specs" / "systems-design.md"

    if vision_path.is_file():
        content = vision_path.read_text().strip()
        if content:
            parts.append(f"### Project Vision\n{content[:600]}")

    if systems_path.is_file():
        content = systems_path.read_text().strip()
        if content:
            parts.append(f"### Systems Design\n{content[:800]}")

    if not parts:
        return ""

    summary = "\n\n".join(parts)
    if len(summary) > 1500:
        summary = summary[:1500] + "\n..."
    return f"## Architecture Context\n\n{summary}\n"


def _find_spec_content(feature: Feature, project_dir: Path) -> str:
    """Find and read the spec file for a feature. Returns content or empty string.

    Searches .specs/features/**/*.md for a file whose stem matches the
    feature name. Called once per feature and cached across retries.
    """
    spec_dir = project_dir / ".specs" / "features"
    if not spec_dir.is_dir():
        return ""
    target = feature.name.lower().replace(" ", "-")
    for p in spec_dir.rglob("*.md"):
        if target in p.stem.lower():
            try:
                return p.read_text()
            except OSError:
                return ""
    return ""


def _build_user_prompt(
    feature: Feature,
    project_dir: Path,
    codebase_summary: str = "",
    *,
    kg_section: str = "",
) -> str:
    """Build the user prompt with the feature spec and context."""
    spec_dir = project_dir / ".specs" / "features"
    spec_content = ""
    spec_path = ""

    # Find the spec file for this feature
    if spec_dir.is_dir():
        for p in spec_dir.rglob("*.md"):
            if feature.name.lower().replace(" ", "-") in p.stem.lower():
                spec_content = p.read_text()
                spec_path = str(p.relative_to(project_dir))
                break

    if not spec_content:
        spec_content = f"Implement the feature: {feature.name}"

    parts = [
        f"Implement the following feature:\n\n"
        f"Feature: {feature.name}\n"
        f"Complexity: {feature.complexity}\n"
        f"Spec file: {spec_path}\n\n"
        f"Specification:\n{spec_content}\n",
    ]

    # Inject architecture context (vision + systems design)
    arch_summary = _read_arch_summary(project_dir)
    if arch_summary:
        parts.append(f"\n{arch_summary}")

    # Inject design patterns only for UI features (skip for backend/data)
    if _is_ui_feature(spec_content):
        patterns_path = project_dir / ".specs" / "design-system" / "patterns.md"
        if patterns_path.is_file():
            patterns_content = patterns_path.read_text()
            if patterns_content.strip():
                parts.append(
                    f"\n## Design Patterns (apply to all components)\n\n"
                    f"{patterns_content}\n"
                )
    else:
        logger.debug(
            "Skipping design patterns for non-UI feature: %s",
            feature.name,
        )

    if codebase_summary:
        parts.append(f"\n## Codebase Context\n\n{codebase_summary}\n")

    if feature.deps:
        dep_exports = _scan_dep_exports(project_dir)
        if dep_exports:
            parts.append(f"\n{dep_exports}")
            parts.append(
                "\nUse the imports above directly. Do NOT spend turns reading "
                "these files — their export signatures are already provided.\n"
            )

    if kg_section:
        parts.append(f"\n{kg_section}")

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
        max_retries: int = 2,
        main_branch: str = "main",
        auto_approve: bool = False,
        eg6_warn_only: bool = True,
    ) -> None:
        self.config = model_config
        self.project_dir = project_dir.resolve()
        self._build_cmd_explicit = build_cmd  # empty = auto-detect
        self._test_cmd_explicit = test_cmd
        self.build_cmd = build_cmd or detect_build_cmd(self.project_dir)
        self.test_cmd = test_cmd or detect_test_cmd(self.project_dir)
        self.max_features = max_features
        self.max_retries = max_retries
        self.main_branch = main_branch
        self.auto_approve = auto_approve
        self.eg6_warn_only = eg6_warn_only
        self._codebase_summary: str = ""
        self._campaign_blocked: list[str] = []  # cross-feature EG1 rejections
        self._campaign_id: str = ""

        # KG integration — optional; None if unavailable
        self._kg: Any = None  # KnowledgeStore | None
        self._kg_stack: str | None = None
        self._kg_injected_ids: list[str] = []
        if _KG_MODULE_AVAILABLE:
            kg_db = str(self.project_dir / ".sdd-knowledge" / "knowledge.db")
            self._kg = _init_store_optional(kg_db)
            self._kg_stack = _detect_project_stack(self.project_dir)

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
        self._campaign_id = state.campaign_id

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
        self._warmup_project_deps()
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
        failed_features: set[str] = set()

        # ── Per-feature loop ─────────────────────────────────────────
        for idx in range(limit):
            feature = features[idx]
            feature_start = int(time.time())

            # Skip features whose dependencies failed
            failed_deps = [d for d in feature.deps if d in failed_features]
            if failed_deps:
                self.skipped += 1
                _status(
                    f"⊘ {feature.name} skipped — depends on failed: "
                    f"{', '.join(failed_deps)}"
                )
                logger.warning(
                    "⊘ %s skipped — depends on failed: %s",
                    feature.name, ", ".join(failed_deps),
                )
                failed_features.add(feature.name)
                continue

            _status(
                f"═══ [{idx + 1}/{limit}] Feature: {feature.name} "
                f"(complexity: {feature.complexity}) ═══"
            )
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
                _status(f"✓ {feature.name} built in {_format_duration(duration)}")
                logger.info(
                    "✓ %s built in %s", feature.name, _format_duration(duration),
                )
            else:
                self.failed += 1
                failed_features.add(feature.name)
                _status(f"✗ {feature.name} failed after {_format_duration(duration)}")
                logger.warning(
                    "✗ %s failed after %s", feature.name, _format_duration(duration),
                )

        # ── Summary ──────────────────────────────────────────────────
        total_duration = int(time.time()) - start_time
        _status(
            f"═══ Build loop complete: {self.built} built, {self.failed} failed, "
            f"{self.skipped} skipped ({_format_duration(total_duration)}) ═══"
        )
        logger.info(
            "═══ Build loop complete: %d built, %d failed, %d skipped (%s) ═══",
            self.built, self.failed, self.skipped,
            _format_duration(total_duration),
        )

        self._write_summary(total_duration)
        self._run_promotion()
        if self._kg:
            self._kg.close()

        # Post-campaign cleanup
        cleanup_merged_branches(self.project_dir, self.main_branch)

        # Clean resume state on full success (no failures)
        if self.failed == 0:
            clean_state(self.project_dir)

        return 1 if self.failed > 0 else 0

    # ── Preflight summary ────────────────────────────────────────────

    def _warmup_project_deps(self) -> None:
        """Install project dependencies if marker files exist but install dirs don't.

        Checks for common package managers and runs install commands:
        - Node: package.json exists but node_modules/ doesn't → npm install
        - Python: pyproject.toml/requirements.txt exists but .venv/ doesn't → pip install
        - Rust: Cargo.toml exists but target/ doesn't → cargo build
        - Go: go.mod exists but vendor/ doesn't → go mod download
        """
        p = self.project_dir

        warmups: list[tuple[str, str, str, str]] = [
            ("package.json", "node_modules", "npm install", "node"),
            ("pyproject.toml", ".venv", "python3 -m venv .venv && .venv/bin/pip install -e .", "python"),
            ("requirements.txt", ".venv", "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt", "python"),
            ("Cargo.toml", "target", "cargo build", "rust"),
            ("go.mod", "vendor", "go mod download", "go"),
        ]

        for marker, install_dir, cmd, label in warmups:
            if (p / marker).is_file() and not (p / install_dir).is_dir():
                _status(f"WARMUP: {label} deps not installed, running: {cmd}")
                logger.info("Warmup: %s detected, installing deps", label)
                try:
                    result = subprocess.run(
                        cmd, shell=True,
                        capture_output=True, text=True,
                        timeout=300,
                        cwd=str(p),
                    )
                    if result.returncode == 0:
                        logger.info("Warmup: %s install complete", label)
                    else:
                        logger.warning(
                            "Warmup: %s install failed (rc=%d): %s",
                            label, result.returncode, result.stderr[-200:],
                        )
                except subprocess.TimeoutExpired:
                    logger.warning("Warmup: %s install timed out after 300s", label)

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

        last_gate_error: str = ""
        last_diff: str = ""
        last_failed_gate: str = ""
        last_error_codes: list[str] = []
        last_reflection: dict | None = None
        base_max_turns = self.config.max_turns
        scaled_turns = _turns_for_complexity(feature.complexity, base_max_turns)
        self.config.max_turns = scaled_turns
        logger.info(
            "Turn budget: %d (base=%d, complexity=%s)",
            scaled_turns, base_max_turns, feature.complexity,
        )

        # Capture baseline once per feature — retries reset to this state,
        # so head_before and baseline_test_count are stable across attempts.
        head_before = _get_head(self.project_dir)
        baseline_test_result = check_tests(
            self.test_cmd, self.project_dir,
        )
        baseline_test_count = baseline_test_result.test_count

        # Cache test file discovery and spec content — stable across retries
        # (agent can't modify test files, and spec files don't change mid-build).
        protected = _discover_test_files(self.project_dir, self.test_cmd)
        feature_spec_content = _find_spec_content(feature, self.project_dir)

        # Reset injected IDs once per feature (not per attempt) so retries
        # that return no KG results still reference the first-attempt injection.
        self._kg_injected_ids = []
        for attempt in range(self.max_retries + 1):
            attempt_start = time.time()
            if attempt > 0:
                _status(f"RETRY {attempt}/{self.max_retries} for {feature.name}")
                logger.info(
                    "Retry %d/%d for %s",
                    attempt, self.max_retries, feature.name,
                )

            # ── SELECT ───────────────────────────────────────────────

            # KG: single query for both relevant knowledge and hardened clues
            kg_section = ""
            kg_clues = ""
            if _KG_MODULE_AVAILABLE and self._kg is not None:
                error_for_query = last_gate_error if attempt > 0 else None
                _spec_query = (
                    f"{feature.name}\n{feature_spec_content}"
                    if feature_spec_content else feature.name
                )
                kg_section, kg_clues, new_ids = _inject_knowledge_combined(
                    self._kg,
                    feature_spec=_spec_query,
                    stack=self._kg_stack,
                    error_pattern=error_for_query,
                )
                # Only overwrite if this attempt returned results; otherwise
                # keep IDs from the last successful query (preserves tracking).
                if new_ids:
                    self._kg_injected_ids = new_ids

            # Build prompts
            system_prompt = _build_system_prompt(
                feature, self.project_dir, self._campaign_blocked,
                kg_clues=kg_clues,
            )
            user_prompt = _build_user_prompt(
                feature, self.project_dir, self._codebase_summary,
                kg_section=kg_section,
            )

            # Inject previous failure context so agent can self-correct
            if last_gate_error and attempt > 0:
                user_prompt += (
                    f"\n\n## PREVIOUS ATTEMPT FAILED\n"
                    f"Your previous implementation failed verification:\n"
                    f"{_smart_truncate(last_gate_error, 5000)}\n\n"
                )
                # Show agent what it wrote so it doesn't waste turns re-reading
                if last_diff:
                    user_prompt += (
                        f"## YOUR PREVIOUS CHANGES (git diff)\n"
                        f"```diff\n{last_diff}\n```\n\n"
                    )
                # Targeted retry guidance based on failure type
                user_prompt += _retry_guidance(last_failed_gate, last_error_codes)
                # Append structured reflection if available
                if last_reflection is not None and _KG_MODULE_AVAILABLE:
                    user_prompt += _format_reflection_for_prompt(last_reflection)

            # Create executor (EG1 gate) scoped to this feature
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
            _status(f"BUILD: invoking agent ({self.config.model})")
            logger.info("BUILD: invoking agent (%s)", self.config.model)

            agent_result: AgentResult = run_local_agent(
                config=self.config,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tools=BUILD_AGENT_TOOLS,
                executor=executor,
            )

            # Collect blocked patterns for cross-feature learning
            if executor.blocked_patterns:
                for p in executor.blocked_patterns:
                    if p not in self._campaign_blocked:
                        self._campaign_blocked.append(p)
                logger.info(
                    "EG1 blocked %d pattern(s) this attempt, %d campaign total",
                    len(executor.blocked_patterns),
                    len(self._campaign_blocked),
                )

            if not agent_result.success:
                logger.warning(
                    "BUILD failed: %s (turns=%d, reason=%s)",
                    agent_result.error,
                    agent_result.turn_count,
                    agent_result.finish_reason,
                )
                # Capture diff before git reset wipes the agent's changes
                last_diff = _get_diff(self.project_dir, head_before)
                last_failed_gate = "BUILD"
                last_error_codes = []
                last_gate_error = f"BUILD: {agent_result.error}"
                last_reflection = self._reflect_and_capture(
                    feature, "BUILD", agent_result.error or "",
                    agent_result.output or "",
                )
                self._record(feature, "failed", attempt,
                             error=agent_result.error,
                             duration=int(time.time() - attempt_start),
                             turn_count=agent_result.turn_count,
                             tool_call_count=len(agent_result.tool_calls))
                self._kg_post_gate(
                    feature=feature,
                    attempt=attempt,
                    outcome="failure",
                    gate_failed="BUILD",
                    error_pattern=agent_result.error,
                    agent_output=agent_result.output or "",
                    duration=time.time() - attempt_start,
                )
                if attempt < self.max_retries:
                    if attempt >= 1:
                        self._git_reset(head_before)
                    continue
                delete_feature_branch(
                    self.project_dir, branch_name, self.main_branch,
                )
                return False

            # ── AUTO-COMPLETE: commit and signals if model forgot ────
            # Models write files and stop without committing or emitting
            # signals. Same principle as translation — if the model can't
            # do it, do it in Python.
            agent_result = self._auto_complete_if_needed(
                agent_result, executor, feature, branch_name,
            )

            # ── GATE (EG2 → EG3 → EG4 → EG5) ───────────────────────
            # All checks deterministic, orchestrator-side, short-circuit
            gate = self._run_gate(
                agent_result=agent_result,
                head_before=head_before,
                baseline_test_count=baseline_test_count,
                feature=feature,
            )

            if not gate.passed:
                # Auto-clean: if EG5 failed on tree_clean only (framework
                # artifacts like next-env.d.ts, tsconfig.tsbuildinfo), add
                # them to the commit and re-check without burning a retry.
                if gate.failed_gate == "EG5" and gate.eg5_commit and any(
                    e.code == "TREE_DIRTY" for e in gate.eg5_commit.checks_failed
                ):
                    cleaned = self._auto_clean_artifacts()
                    if cleaned:
                        _status(f"EG5 auto-clean: committed {cleaned} artifact(s), re-checking")
                        logger.info("EG5 auto-clean: committed %d artifact(s)", cleaned)
                        gate = self._run_gate(
                            agent_result=agent_result,
                            head_before=head_before,
                            baseline_test_count=baseline_test_count,
                            feature=feature,
                        )

            if not gate.passed:
                _status(f"GATE FAILED at {gate.failed_gate}: {gate.error[:200]}")
                logger.warning(
                    "GATE FAILED at %s: %s", gate.failed_gate, gate.error,
                )
                # Capture diff before git reset wipes the agent's changes
                last_diff = _get_diff(self.project_dir, head_before)
                last_failed_gate = gate.failed_gate
                last_error_codes = _extract_error_codes(gate)
                last_gate_error = f"{gate.failed_gate}: {gate.error}"
                last_reflection = self._reflect_and_capture(
                    feature, gate.failed_gate, gate.error,
                    agent_result.output or "",
                )
                self._record(feature, "failed", attempt,
                             error=last_gate_error,
                             duration=int(time.time() - attempt_start),
                             turn_count=agent_result.turn_count,
                             tool_call_count=len(agent_result.tool_calls))
                self._kg_post_gate(
                    feature=feature,
                    attempt=attempt,
                    outcome="failure",
                    gate_failed=gate.failed_gate,
                    error_pattern=gate.error,
                    agent_output=agent_result.output or "",
                    duration=time.time() - attempt_start,
                )
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
                self._record(feature, "failed", attempt, error=str(exc),
                             duration=int(time.time() - attempt_start),
                             turn_count=agent_result.turn_count,
                             tool_call_count=len(agent_result.tool_calls))
                self._kg_post_gate(
                    feature=feature,
                    attempt=attempt,
                    outcome="failure",
                    gate_failed="MERGE",
                    error_pattern=str(exc),
                    duration=time.time() - attempt_start,
                )
                delete_feature_branch(
                    self.project_dir, branch_name, self.main_branch,
                )
                return False

            self._record(
                feature, "built", attempt,
                test_count=current_test_count,
                duration=int(time.time() - attempt_start),
                turn_count=agent_result.turn_count,
                tool_call_count=len(agent_result.tool_calls),
            )

            # Refresh codebase summary after merge so the next feature
            # sees an up-to-date view of the project (new modules, exports).
            try:
                self._codebase_summary = generate_codebase_summary(
                    self.project_dir, self.config,
                )
            except Exception as exc:
                logger.warning("Codebase summary refresh failed (continuing): %s", exc)

            self._kg_post_gate(
                feature=feature,
                attempt=attempt,
                outcome="success",
                agent_output=agent_result.output or "",
                duration=time.time() - attempt_start,
            )
            return True

        # Exhausted all retries — clean up the feature branch
        delete_feature_branch(
            self.project_dir, branch_name, self.main_branch,
        )
        return False

    # ── KG capture helper ─────────────────────────────────────────

    def _kg_post_gate(
        self,
        feature: Feature,
        attempt: int,
        outcome: str,
        *,
        gate_failed: str | None = None,
        error_pattern: str | None = None,
        agent_output: str = "",
        duration: float | None = None,
    ) -> None:
        """Record build outcome to KG. No-op if KG unavailable."""
        if not _KG_MODULE_AVAILABLE or self._kg is None:
            return
        _kg_post_gate_fn(
            self._kg,
            feature_name=feature.name,
            campaign_id=self._campaign_id or None,
            injected_ids=self._kg_injected_ids,
            attempt=attempt,
            outcome=outcome,
            gate_failed=gate_failed,
            error_pattern=error_pattern,
            duration=duration,
            agent_output=agent_output,
            stack=self._kg_stack,
        )

    # ── Structured reflection ────────────────────────────────────

    def _make_llm_call(self, prompt: str) -> str:
        """Single-turn LLM completion (no tools) for reflection/synthesis.

        Reuses the same model server as the build agent but with no tools
        and max_tokens capped to keep it cheap and fast.
        """
        from openai import OpenAI
        client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
        )
        role = self.config.system_role
        resp = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": role, "content": "You are a concise engineering analyst."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=512,
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""

    def _reflect_and_capture(
        self,
        feature: Feature,
        gate_failed: str,
        error_pattern: str,
        agent_output: str,
    ) -> dict | None:
        """Run structured reflection on a failure, capture to KG.

        Returns the reflection dict (for prompt injection) or None.
        """
        if not _KG_MODULE_AVAILABLE:
            return None
        try:
            reflection = _reflect_on_failure(
                llm_call=self._make_llm_call,
                feature_name=feature.name,
                gate_failed=gate_failed,
                error_pattern=error_pattern,
                agent_output=agent_output,
            )
            if reflection:
                _capture_reflection(
                    self._kg,
                    reflection,
                    feature_name=feature.name,
                    gate_failed=gate_failed,
                    campaign_id=getattr(self, "_campaign_id", None),
                )
            return reflection
        except Exception as exc:
            logger.warning("KG: reflection failed (continuing): %s", exc)
            return None

    # ── Post-campaign promotion + synthesis ───────────────────────

    def _run_promotion(self) -> None:
        """Run KG promotion and cluster synthesis after a campaign."""
        if not _KG_MODULE_AVAILABLE or self._kg is None:
            return
        try:
            events = self._kg.promote()
            if events:
                promoted = sum(
                    1 for e in events
                    if e.get("from") == "active" and e.get("to") == "promoted"
                )
                hardened = sum(1 for e in events if e.get("to") == "hardened")
                demoted = sum(
                    1 for e in events
                    if e.get("from") == "hardened" and e.get("to") == "promoted"
                )
                logger.info(
                    "KG promotion: %d promoted, %d hardened, %d demoted",
                    promoted, hardened, demoted,
                )
            else:
                logger.info("KG promotion: no changes")
        except Exception as exc:
            logger.warning("KG promotion failed (continuing): %s", exc)

        # Synthesize universals from unlinked clusters
        try:
            results = _synthesize_universals(
                self._kg,
                llm_call=self._make_llm_call,
                max_synthesize=5,
                campaign_id=getattr(self, "_campaign_id", None),
            )
            if results:
                logger.info(
                    "KG synthesis: created %d universal(s): %s",
                    len(results),
                    [r["title"][:60] for r in results],
                )
        except Exception as exc:
            logger.warning("KG synthesis failed (continuing): %s", exc)

    # ── GATE: deterministic ExecGate checks (EG2–EG5) ─────────────

    def _auto_complete_if_needed(
        self,
        agent_result: AgentResult,
        executor: BuildAgentExecutor,
        feature: Feature,
        branch_name: str,
    ) -> AgentResult:
        """Auto-commit and inject signals if model forgot.

        Models write files and stop without committing or emitting
        FEATURE_BUILT signals. Rather than failing at EG2, detect
        the situation and complete the loop in Python.

        Note: does NOT force agent_result.success — EG2 will still
        validate the injected signals against disk state.
        """
        output = agent_result.output or ""
        has_signal = "FEATURE_BUILT" in output
        has_written = bool(executor._written_files)

        if has_signal or not has_written:
            return agent_result

        logger.info(
            "Auto-complete: agent wrote %d file(s) but didn't signal. "
            "Committing and injecting signals.",
            len(executor._written_files),
        )

        # Derive source files from executor's write log (trusted, not agent-declared)
        source_files = []
        for f in executor._written_files:
            try:
                rel = str(Path(f).relative_to(self.project_dir))
                source_files.append(rel)
            except ValueError:
                source_files.append(f)

        # Auto-commit only the files the agent actually wrote — never `git add -A`
        # which could stage untracked temp files, debug logs, or other artifacts.
        try:
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True,
                cwd=str(self.project_dir),
            )
            if status.stdout.strip():
                for sf in source_files:
                    subprocess.run(
                        ["git", "add", "--", sf],
                        capture_output=True, text=True,
                        cwd=str(self.project_dir),
                    )
                subprocess.run(
                    ["git", "commit", "-m",
                     f"Auto-commit: {feature.name} (agent forgot to commit)"],
                    capture_output=True, text=True,
                    cwd=str(self.project_dir),
                )
                logger.info("Auto-complete: committed %d file(s)", len(source_files))
        except Exception as exc:
            logger.warning("Auto-complete: git commit failed: %s", exc)

        # Find the spec file
        spec_file = ""
        spec_dir = self.project_dir / ".specs" / "features"
        if spec_dir.is_dir():
            slug = feature.name.lower().replace(" ", "-")
            for p in spec_dir.rglob("*.md"):
                if slug in p.stem.lower():
                    spec_file = str(p.relative_to(self.project_dir))
                    break

        # Inject signals into agent output — EG2 will still validate them
        signals = (
            f"\nFEATURE_BUILT: {feature.name}\n"
            f"SPEC_FILE: {spec_file}\n"
            f"SOURCE_FILES: {','.join(source_files)}\n"
        )
        agent_result.output = output + signals
        # Do NOT set agent_result.success = True here. The original
        # agent status is preserved; EG2 validates the injected signals.
        logger.info("Auto-complete: injected signals for %s", feature.name)
        return agent_result

    def _run_gate(
        self,
        agent_result: AgentResult,
        head_before: str,
        baseline_test_count: int | None,
        feature: Feature | None = None,
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
            expected_feature=feature.name if feature else "",
        )
        gate.eg2_signals = signals

        if not signals.valid:
            gate.failed_gate = "EG2"
            gate.error = "; ".join(e.detail for e in signals.errors)
            return gate

        logger.info(
            "EG2: signals valid (feature=%s, spec=%s, sources=%d)",
            signals.feature_name, signals.spec_file,
            len(signals.source_files),
        )
        _status(f"EG2 ✓ signals valid (sources={len(signals.source_files)})")

        # ── EG3: Build check ─────────────────────────────────────
        # Re-detect build command: agent may have created app/ or pages/
        # this turn, upgrading the check from tsc to next build.
        if not self._build_cmd_explicit:
            self.build_cmd = detect_build_cmd(self.project_dir)
        build_result = check_build(self.build_cmd, self.project_dir)
        gate.eg3_build = build_result

        if not build_result.passed:
            gate.failed_gate = "EG3"
            gate.error = f"Build failed: {build_result.output[-2000:]}"
            return gate

        _status("EG3 ✓ build passed")

        # ── EG4: Test check ──────────────────────────────────────
        test_result = check_tests(self.test_cmd, self.project_dir)
        gate.eg4_tests = test_result

        if not test_result.passed:
            gate.failed_gate = "EG4"
            gate.error = f"Tests failed: {test_result.output[-2000:]}"
            return gate

        _status(f"EG4 ✓ tests passed (count={test_result.test_count})")

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

        _status("EG5 ✓ commit authorized")

        # ── EG6: Spec adherence ─────────────────────────────────
        adherence_result = check_spec_adherence(
            project_dir=self.project_dir,
            source_files=signals.source_files,
            base_commit=head_before,
        )
        gate.eg6_adherence = adherence_result

        if not adherence_result.passed:
            if self.eg6_warn_only:
                # Warn mode: log deviations but don't block the build.
                # Use this to validate EG6 checks against real campaigns
                # before enforcing. Switch to enforce with --eg6-enforce.
                logger.warning(
                    "EG6 WARN (not blocking): %s", adherence_result.summary,
                )
                _status(f"EG6 ⚠ spec adherence warnings: {adherence_result.summary[:200]}")
            else:
                gate.failed_gate = "EG6"
                gate.error = adherence_result.summary
                return gate
        else:
            _status(f"EG6 ✓ spec adherence ({len(adherence_result.checks_passed)} checks)")

        # All checks passed
        gate.passed = True
        _status("GATE: all checks passed ✓")
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
        duration: int = 0,
        turn_count: int = 0,
        tool_call_count: int = 0,
    ) -> None:
        """Record a feature build result."""
        self.records.append(FeatureRecord(
            name=feature.name,
            status=status,
            attempt=attempt,
            error=error,
            test_count=test_count,
            duration=duration,
            turn_count=turn_count,
            tool_call_count=tool_call_count,
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

    # Known framework artifacts that are generated by build/test tools,
    # not by the agent. Safe to auto-commit when EG5 tree_clean fails.
    _KNOWN_ARTIFACTS: frozenset[str] = frozenset({
        "next-env.d.ts",
        "tsconfig.tsbuildinfo",
        ".tsbuildinfo",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".next",
        ".nuxt",
        ".svelte-kit",
        "dist",
    })

    def _auto_clean_artifacts(self) -> int:
        """Auto-commit known framework artifacts that block EG5 tree_clean.

        Returns the number of files committed, or 0 if nothing was cleaned.
        Only commits files whose names are in _KNOWN_ARTIFACTS. Unknown
        files are left alone — they trigger a normal retry.
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True,
                cwd=str(self.project_dir), timeout=10,
            )
            if not result.stdout.strip():
                return 0

            lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            files = []
            for line in lines:
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    files.append(parts[1].strip())

            all_known = all(
                any(f.endswith(a) or f == a or f.startswith(a + "/")
                    for a in self._KNOWN_ARTIFACTS)
                for f in files
            )
            if not all_known:
                logger.info(
                    "EG5 auto-clean: unknown untracked files, skipping: %s",
                    ", ".join(files),
                )
                return 0

            subprocess.run(
                ["git", "add", "-A"],
                cwd=str(self.project_dir),
                capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "commit", "--amend", "--no-edit"],
                cwd=str(self.project_dir),
                capture_output=True, timeout=10,
            )
            return len(files)
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("EG5 auto-clean failed: %s", exc)
            return 0

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
                    "duration_seconds": r.duration,
                    "duration_human": _format_duration(r.duration),
                    "turn_count": r.turn_count,
                    "tool_call_count": r.tool_call_count,
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
        default=int(os.environ.get("MAX_RETRIES", "2")),
        help="Max retries per feature (default: 2)",
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
        "--pre-build-only",
        action="store_true",
        default=False,
        help="Run pre-build phases (1-6) then exit (no build loop)",
    )
    parser.add_argument(
        "--vision-input",
        default=os.environ.get("VISION_INPUT", ""),
        help="User input for Phase 1 (VISION). Required if --pre-build and no .specs/vision.md",
    )
    parser.add_argument(
        "--eg6-enforce",
        action="store_true",
        default=False,
        help="Enforce EG6 spec adherence (default: warn-only mode, logs but doesn't block)",
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
    if args.pre_build or args.pre_build_only:
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

        if args.pre_build_only:
            sys.exit(0)

    # Run the loop
    loop = BuildLoopV2(
        model_config=config,
        project_dir=project_dir,
        build_cmd=args.build_cmd,
        test_cmd=args.test_cmd,
        max_features=args.max_features,
        max_retries=args.max_retries,
        auto_approve=args.auto_approve,
        eg6_warn_only=not args.eg6_enforce,
    )

    exit_code = loop.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
