"""Generate a concise codebase summary for build agent prompts.

Uses the local agent (GPT-OSS-120B) to analyze the project's file tree
and produce a structural summary. Cached by git tree hash so repeated
calls for the same tree state are free.

Falls back to empty string on any failure — the build loop must never
crash because of summary generation.

Public API:
    generate_codebase_summary(project_dir, config) -> str
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


_EXCLUDED_DIRS: frozenset[str] = frozenset({
    "node_modules", ".git", "dist", "build", ".next",
    "__pycache__", "target", ".build-worktrees", "venv", ".venv",
    ".auto-sdd-cache", ".sdd-config", ".sdd-state", ".specs",
})

_FILE_TREE_CAP: int = 500

_AGENT_PROMPT: str = """\
You are a codebase analyst. Below is the file tree of a software project.
Produce a structured summary covering:

1. **Key modules / entry points** — the main files that drive the application
2. **Public types and interfaces** — important data structures, API contracts
3. **Import / dependency relationships** — how modules connect to each other
4. **Architectural patterns** — framework usage, layering, notable conventions

Constraints:
- Output no more than 100 lines.
- Use compact markdown (##, bullets, short descriptions).
- Work from the file tree below. Read only the files you need to understand
  the structure — do not read every file.

## File Tree

```
{file_tree}
```
"""


# ── File tree generation ─────────────────────────────────────────────────────


def _generate_file_tree(project_dir: Path) -> str:
    """Walk project_dir, return newline-separated relative paths.

    Respects _EXCLUDED_DIRS and caps at _FILE_TREE_CAP files.
    """
    paths: list[str] = []
    stack: list[Path] = [project_dir]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name not in _EXCLUDED_DIRS:
                    stack.append(entry)
            elif entry.is_file():
                if len(paths) >= _FILE_TREE_CAP:
                    paths.append(f"... (truncated at {_FILE_TREE_CAP} files)")
                    return "\n".join(paths)
                paths.append(str(entry.relative_to(project_dir)))
    paths.sort()
    return "\n".join(paths)


# ── Git tree hash ────────────────────────────────────────────────────────────


def _get_tree_hash(project_dir: Path) -> str | None:
    """Return the git tree hash, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"],
            capture_output=True, text=True,
            cwd=str(project_dir), timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


# ── Cache layer ──────────────────────────────────────────────────────────────


def _cache_dir(project_dir: Path) -> Path:
    return project_dir / ".auto-sdd-cache"


def _cache_path(project_dir: Path, tree_hash: str) -> Path:
    return _cache_dir(project_dir) / f"codebase-summary-{tree_hash}.md"


def _read_cache(project_dir: Path, tree_hash: str) -> str | None:
    """Return cached summary if it exists, otherwise None."""
    path = _cache_path(project_dir, tree_hash)
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            pass
    return None


def _write_cache(project_dir: Path, tree_hash: str, content: str) -> None:
    """Write content to cache. Creates .gitignore to exclude cache dir."""
    cache = _cache_dir(project_dir)
    cache.mkdir(parents=True, exist_ok=True)
    gitignore = cache / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n")
    _cache_path(project_dir, tree_hash).write_text(content, encoding="utf-8")


# ── Agent call (V2: uses run_local_agent) ────────────────────────────────────


def _call_agent(file_tree: str, config: object) -> str:
    """Invoke local agent to produce a codebase summary.

    Uses run_local_agent with read_file tool only — the summary agent
    doesn't need to write anything.

    Args:
        file_tree: Newline-separated file listing.
        config: ModelConfig instance.

    Raises on any failure — caller handles fallback.
    """
    from auto_sdd.lib.local_agent import run_local_agent

    prompt = _AGENT_PROMPT.format(file_tree=file_tree)

    result = run_local_agent(
        config=config,
        system_prompt="You are a codebase analyst. Respond with a concise structural summary.",
        user_prompt=prompt,
        tools=None,
        executor=None,
    )

    if not result.success or not result.output.strip():
        raise RuntimeError(f"Summary agent failed: {result.error or 'empty output'}")

    return result.output.strip()


# ── Learnings ────────────────────────────────────────────────────────────────

_LEARNINGS_CAP: int = 40


def _read_recent_learnings(project_dir: Path) -> str:
    """Read recent learnings from .specs/learnings/ and return as text.

    Returns empty string when the directory is missing or empty.
    """
    learnings_dir = project_dir / ".specs" / "learnings"
    if not learnings_dir.is_dir():
        return ""

    md_files = sorted(learnings_dir.glob("*.md"))
    lines: list[str] = []

    for md_file in md_files:
        if not md_file.is_file() or md_file.stat().st_size == 0:
            continue
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines.append(f"### {md_file.name}")
        lines.extend(content.split("\n"))

    if not lines:
        return ""

    capped = lines[:_LEARNINGS_CAP]
    if len(lines) > _LEARNINGS_CAP:
        capped.append(f"... (learnings truncated at {_LEARNINGS_CAP} lines)")

    return "\n".join(["## Recent Learnings", "", *capped, ""])


# ── Public API ───────────────────────────────────────────────────────────────


def generate_codebase_summary(
    project_dir: Path,
    config: object | None = None,
) -> str:
    """Generate a structured codebase summary.

    Cached by git tree hash. Falls back to empty string on any failure.

    Args:
        project_dir: Absolute path to the project.
        config: ModelConfig for the agent call. If None, returns
                file-tree-only summary (no agent, useful for testing).

    Returns:
        Structured summary string, or empty string on failure.
    """
    if not project_dir.is_dir():
        logger.warning("Not a directory: %s", project_dir)
        return ""

    logger.info("Generating codebase summary for %s", project_dir)

    # 1. Generate file tree
    file_tree = _generate_file_tree(project_dir)
    if not file_tree:
        return ""

    # 2. Check cache
    tree_hash = _get_tree_hash(project_dir)
    if tree_hash is not None:
        cached = _read_cache(project_dir, tree_hash)
        if cached is not None:
            logger.info("Cache hit for tree hash %s", tree_hash)
            learnings = _read_recent_learnings(project_dir)
            return cached + "\n" + learnings if learnings else cached

    # 3. Call agent (skip if no config provided)
    agent_summary = ""
    if config is not None:
        try:
            agent_summary = _call_agent(file_tree, config)
        except Exception:
            logger.warning("Agent call failed; returning empty summary", exc_info=True)

    # 4. Cache result
    if tree_hash is not None and agent_summary:
        try:
            _write_cache(project_dir, tree_hash, agent_summary)
            logger.info("Cached summary for tree hash %s", tree_hash)
        except OSError:
            logger.warning("Failed to write cache", exc_info=True)

    # 5. Append learnings
    learnings = _read_recent_learnings(project_dir)
    if learnings and agent_summary:
        return agent_summary + "\n" + learnings
    if learnings:
        return learnings
    return agent_summary
