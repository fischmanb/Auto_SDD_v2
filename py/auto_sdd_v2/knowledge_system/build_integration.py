"""Knowledge system integration helpers for the build loop and pre-build phases.

All public functions are optional-safe: if *store* is None they return empty
strings or are no-ops.  No LLM judgment here — all SQL-backed deterministic
queries and plain-text extraction.

Token budgets
-------------
_USER_PROMPT_MAX_TOKENS  : max tokens injected into the build user prompt
_SYSTEM_PROMPT_MAX_TOKENS: max tokens injected into the build system prompt
_SPEC_PROMPT_MAX_TOKENS  : max tokens injected into the spec-first user prompt
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auto_sdd_v2.knowledge_system.store import KnowledgeStore

logger = logging.getLogger(__name__)

# ── Token budgets ─────────────────────────────────────────────────────────────

_CHARS_PER_TOKEN = 4          # conservative 4 chars ≈ 1 token
_USER_PROMPT_MAX_TOKENS = 2000
_SYSTEM_PROMPT_MAX_TOKENS = 1000
_SPEC_PROMPT_MAX_TOKENS = 500


def _truncate(text: str, max_tokens: int) -> str:
    max_chars = max_tokens * _CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[truncated to fit token budget]"


# ── Store initialization ──────────────────────────────────────────────────────


def init_store_optional(db_path: str) -> "KnowledgeStore | None":
    """Open KnowledgeStore at *db_path*, creating parent dirs as needed.

    Returns None if initialization fails for any reason. Callers treat None
    as "KG unavailable" and continue without it — the build must not block.
    """
    try:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        from auto_sdd_v2.knowledge_system.store import KnowledgeStore
        store = KnowledgeStore(db_path)
        logger.info("KnowledgeStore initialized at %s", db_path)
        return store
    except Exception as exc:
        logger.warning(
            "KnowledgeStore init failed — builds continue without KG: %s", exc,
        )
        return None


# ── Stack detection from project directory ────────────────────────────────────


def detect_project_stack(project_dir: Path) -> str | None:
    """Detect the technology stack from project marker files.

    Returns the first matching stack name, or None if unknown.
    """
    p = project_dir
    if (p / "next.config.js").exists() or (p / "next.config.ts").exists():
        return "nextjs"
    if (p / "package.json").exists():
        try:
            pkg = (p / "package.json").read_text(errors="replace")
            if '"react"' in pkg or "'react'" in pkg:
                return "react"
        except OSError:
            pass
        return "typescript"
    if (p / "pyproject.toml").exists() or (p / "setup.py").exists():
        return "python"
    if (p / "requirements.txt").exists():
        return "python"
    if (p / "Cargo.toml").exists():
        return "rust"
    if (p / "go.mod").exists():
        return "go"
    return None


# ── Query helpers ─────────────────────────────────────────────────────────────


def inject_relevant_knowledge(
    store: "KnowledgeStore | None",
    feature_spec: str,
    stack: str | None,
    error_pattern: str | None = None,
    max_results: int = 5,
) -> tuple[str, list[str]]:
    """Query KG for relevant learnings to inject into the build user prompt.

    Returns *(section_text, node_ids)*.  *section_text* is empty when there
    are no results or *store* is None.  *node_ids* is used for outcome
    tracking — pass it back to `kg_post_gate`.
    """
    if store is None:
        return "", []
    try:
        results = store.query(
            stack=stack,
            feature_spec=feature_spec,
            error_pattern=error_pattern,
            max_results=max_results,
        )
        if not results:
            return "", []

        node_ids = [r["id"] for r in results]
        lines: list[str] = ["## Relevant Knowledge\n"]
        for r in results:
            title = r.get("title") or r["content"].split("\n")[0][:300]
            lines.append(
                f"**{r['id']}** ({r['node_type']}, {r['status']}): {title}"
            )
        section = "\n\n".join(lines) + "\n"
        section = _truncate(section, _USER_PROMPT_MAX_TOKENS)
        return section, node_ids

    except Exception as exc:
        logger.warning("KG relevant knowledge query failed (continuing): %s", exc)
        return "", []


def inject_hardened_clues(
    store: "KnowledgeStore | None",
    stack: str | None,
    max_results: int = 5,
) -> str:
    """Query KG for hardened clues to inject into the build system prompt.

    Returns a compact rules string (empty if no results or *store* is None).
    Only nodes with status='hardened' are returned — these are rules that
    have been validated across ≥3 successful builds.
    """
    if store is None:
        return ""
    try:
        results = store.query(
            stack=stack,
            max_results=max_results,
            min_status="hardened",
        )
        if not results:
            return ""

        lines: list[str] = ["\nHARDENED RULES (validated across multiple builds):"]
        for r in results:
            rule = r.get("title") or r["content"].split("\n")[0][:200]
            lines.append(f"- {rule}")
        section = "\n".join(lines) + "\n"
        return _truncate(section, _SYSTEM_PROMPT_MAX_TOKENS)

    except Exception as exc:
        logger.warning("KG hardened clues query failed (continuing): %s", exc)
        return ""


def inject_spec_learnings(
    store: "KnowledgeStore | None",
    stack: str | None,
    max_results: int = 3,
) -> str:
    """Query KG for promoted/hardened learnings to inject into spec writing.

    Returns a '## Project Learnings' section (empty if nothing to inject).
    This informs spec writing, not build execution, so the budget is tighter.
    """
    if store is None:
        return ""
    try:
        results = store.query(
            stack=stack,
            max_results=max_results,
            min_status="promoted",
        )
        if not results:
            return ""

        lines: list[str] = ["\n## Project Learnings\n"]
        for r in results:
            title = r.get("title") or r["content"].split("\n")[0][:300]
            lines.append(f"- **{r['id']}**: {title}")
        section = "\n".join(lines) + "\n"
        return _truncate(section, _SPEC_PROMPT_MAX_TOKENS)

    except Exception as exc:
        logger.warning("KG spec learnings query failed (continuing): %s", exc)
        return ""


# ── Post-gate capture ─────────────────────────────────────────────────────────


def extract_learning_candidates(output: str) -> list[str]:
    """Extract LEARNING_CANDIDATE: lines from agent output.

    Returns a list of bare candidate strings (the text after the signal
    prefix), deduplicated in order.
    """
    seen: set[str] = set()
    candidates: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("LEARNING_CANDIDATE:"):
            text = stripped[len("LEARNING_CANDIDATE:"):].strip()
            if text and text not in seen:
                seen.add(text)
                candidates.append(text)
    return candidates


def kg_post_gate(
    store: "KnowledgeStore | None",
    feature_name: str,
    campaign_id: str | None,
    injected_ids: list[str],
    attempt: int,
    outcome: str,  # "success" | "failure"
    *,
    gate_failed: str | None = None,
    error_pattern: str | None = None,
    duration: float | None = None,
    agent_output: str = "",
    stack: str | None = None,
) -> None:
    """Record a build outcome and capture any learnings. No-op if *store* is None.

    On success:
      - Records outcome row
      - Extracts LEARNING_CANDIDATE: lines from *agent_output* → instance nodes

    On failure:
      - Records outcome row
      - Creates a mistake node from *error_pattern* + *gate_failed* for future
        error-pattern matching in queries
    """
    if store is None:
        return
    try:
        store.record_outcome(
            feature_name=feature_name,
            attempt=attempt,
            outcome=outcome,
            campaign_id=campaign_id,
            node_ids_injected=injected_ids if injected_ids else None,
            gate_failed=gate_failed,
            error_pattern=error_pattern,
            duration=duration,
        )

        # Extract LEARNING_CANDIDATE signals from agent output
        if agent_output:
            for candidate_text in extract_learning_candidates(agent_output):
                node_id = store.add_node(
                    node_type="instance",
                    title=candidate_text[:200],
                    content=candidate_text[:2000],
                    stack=stack,
                    campaign_id=campaign_id,
                    metadata={
                        "source": "LEARNING_CANDIDATE",
                        "feature": feature_name,
                        "attempt": attempt,
                    },
                )
                logger.info("KG: captured LEARNING_CANDIDATE → node %s", node_id)

        # On failure, create a mistake node from the gate error
        if outcome == "failure" and error_pattern and gate_failed:
            node_id = store.add_node(
                node_type="mistake",
                title=f"Gate {gate_failed} failure: {feature_name}"[:200],
                content=error_pattern[:2000],
                stack=stack,
                campaign_id=campaign_id,
                metadata={
                    "gate": gate_failed,
                    "feature": feature_name,
                    "attempt": attempt,
                },
            )
            logger.info(
                "KG: created mistake node %s for %s failure in %s",
                node_id, gate_failed, feature_name,
            )

    except Exception as exc:
        logger.warning("KG post-gate capture failed (continuing): %s", exc)
