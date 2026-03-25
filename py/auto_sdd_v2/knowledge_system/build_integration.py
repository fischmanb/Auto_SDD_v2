"""Knowledge system integration helpers for the build loop and pre-build phases.

All public functions are optional-safe: if *store* is None they return empty
strings or are no-ops.  Deterministic SQL-backed queries and plain-text
extraction throughout, with one explicit exception: ``synthesize_universals``
uses a one-shot LLM call to generate universal node titles/content from
keyword clusters.  Created universals start at ``active`` and must earn
promotion through the normal lift-gated pipeline.

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
            content = r.get("content", "")
            header = f"**{r['id']}** ({r['node_type']}, {r['status']}): {title}"
            # Include full content when it adds information beyond the title
            if content and content.strip() != title.strip():
                # Cap individual node content to keep total size reasonable
                body = content[:1000]
                if len(content) > 1000:
                    body += "…"
                lines.append(f"{header}\n{body}")
            else:
                lines.append(header)
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


def inject_knowledge_combined(
    store: "KnowledgeStore | None",
    feature_spec: str,
    stack: str | None,
    error_pattern: str | None = None,
    max_relevant: int = 5,
    max_hardened: int = 5,
) -> tuple[str, str, list[str]]:
    """Single-query KG injection returning both relevant and hardened sections.

    Performs one query with min_status='active' and a larger result set,
    then partitions results into:
    - Relevant knowledge (for user prompt) — all matched nodes
    - Hardened clues (for system prompt) — only hardened-status nodes

    Returns *(relevant_section, hardened_section, node_ids)*.
    This replaces separate calls to inject_relevant_knowledge +
    inject_hardened_clues, halving the DB round-trips.
    """
    if store is None:
        return "", "", []

    try:
        # Fetch enough results to fill both buckets from a single query.
        # Use feature_spec + error_pattern for relevance ranking.
        results = store.query(
            stack=stack,
            feature_spec=feature_spec,
            error_pattern=error_pattern,
            max_results=max_relevant + max_hardened,
            min_status="active",
        )
        if not results:
            return "", "", []

        # Partition into hardened vs. all
        hardened = [r for r in results if r.get("status") == "hardened"]
        relevant = results[:max_relevant]

        # Build relevant section (user prompt)
        node_ids = [r["id"] for r in relevant]
        rel_lines: list[str] = ["## Relevant Knowledge\n"]
        for r in relevant:
            title = r.get("title") or r["content"].split("\n")[0][:300]
            content = r.get("content", "")
            header = f"**{r['id']}** ({r['node_type']}, {r['status']}): {title}"
            if content and content.strip() != title.strip():
                body = content[:1000]
                if len(content) > 1000:
                    body += "…"
                rel_lines.append(f"{header}\n{body}")
            else:
                rel_lines.append(header)
        relevant_section = "\n\n".join(rel_lines) + "\n"
        relevant_section = _truncate(relevant_section, _USER_PROMPT_MAX_TOKENS)

        # Build hardened section (system prompt)
        hardened_section = ""
        if hardened:
            h_lines: list[str] = ["\nHARDENED RULES (validated across multiple builds):"]
            for r in hardened[:max_hardened]:
                rule = r.get("title") or r["content"].split("\n")[0][:200]
                h_lines.append(f"- {rule}")
            hardened_section = "\n".join(h_lines) + "\n"
            hardened_section = _truncate(hardened_section, _SYSTEM_PROMPT_MAX_TOKENS)

        return relevant_section, hardened_section, node_ids

    except Exception as exc:
        logger.warning("KG combined query failed (continuing): %s", exc)
        return "", "", []


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

        # Track newly created node IDs for generalization linking
        new_node_ids: list[str] = []

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
                new_node_ids.append(node_id)
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
            new_node_ids.append(node_id)
            logger.info(
                "KG: created mistake node %s for %s failure in %s",
                node_id, gate_failed, feature_name,
            )

        # Link new nodes to existing universals via keyword overlap
        for nid in new_node_ids:
            linked = store.link_to_universals(nid)
            if linked:
                logger.info(
                    "KG: linked %s to %d universal(s): %s",
                    nid, len(linked), linked,
                )

    except Exception as exc:
        logger.warning("KG post-gate capture failed (continuing): %s", exc)


# ── Structured reflection ────────────────────────────────────────────────────

# Post-failure LLM reflection: extract a reusable lesson from a failure.
# Runs between gate failure and retry — the extracted rule is:
#   1. Injected into the retry prompt (immediate value)
#   2. Stored as an instance node in the KG (long-term value via promotion)

_REFLECTION_PROMPT = """\
A build attempt just failed.  Analyze the failure and extract a reusable rule.

Feature: {feature_name}
Gate that failed: {gate_failed}
Error:
{error_pattern}

Agent output (last 3000 chars):
{agent_tail}

{gate_context}
Instructions:
1. Identify the ROOT CAUSE (not the symptom).
2. Write a RULE that would prevent this class of failure in future builds.
   - Start with a verb: "Always...", "Never...", "Ensure..."
   - Be specific enough to act on, general enough to reuse
   - Max 2 sentences

Respond with exactly:
CAUSE: <one-sentence root cause>
RULE: <the reusable rule>"""


# Gate-specific analysis hints to improve reflection quality.
# These tell the reflection LLM what to focus on per failure type.
_GATE_REFLECTION_CONTEXT: dict[str, str] = {
    "BUILD": (
        "Analysis context: The agent itself crashed, timed out, or failed to "
        "complete. Common causes: agent entered an infinite read loop, exceeded "
        "turn limit, or encountered an unrecoverable tool error. Focus on what "
        "the agent was doing (from the output tail) and why it got stuck."
    ),
    "EG2": (
        "Analysis context: The agent's output was missing required signals "
        "(FEATURE_BUILT, SPEC_FILE, SOURCE_FILES) or the referenced files "
        "don't exist on disk. Common causes: agent forgot to emit signals, "
        "emitted them inside a code block (gets filtered), or declared files "
        "it didn't actually create. Focus on signal emission and file creation."
    ),
    "EG3": (
        "Analysis context: The project failed to compile after the agent's "
        "changes. Common causes: syntax errors, missing imports, wrong module "
        "paths, type errors, referencing non-existent exports. Focus on the "
        "compiler error message and which files the agent wrote."
    ),
    "EG4": (
        "Analysis context: Tests failed after the agent's changes. Common "
        "causes: agent broke existing functionality, didn't match expected "
        "API contracts, introduced state mutations, or changed shared "
        "utilities. Focus on which tests failed and what behavior changed."
    ),
    "EG5": (
        "Analysis context: Commit authorization failed. Common causes: agent "
        "forgot to git commit, left uncommitted changes, modified files outside "
        "the project scope, or caused test count to drop. Focus on the specific "
        "check that failed (HEAD_UNCHANGED, TREE_DIRTY, TEST_REGRESSION)."
    ),
    "EG6": (
        "Analysis context: Spec adherence failed. The code compiles and tests "
        "pass, but the agent's output doesn't match structural requirements. "
        "Common causes: files placed in wrong directories, SOURCE_FILES signal "
        "doesn't match actual changes, design tokens referenced that don't "
        "exist in tokens.md, or file naming convention violations. Focus on "
        "which adherence check failed and whether it's a signal/placement issue."
    ),
}


def reflect_on_failure(
    llm_call: "callable",
    feature_name: str,
    gate_failed: str,
    error_pattern: str,
    agent_output: str = "",
) -> dict | None:
    """Run a one-shot LLM reflection on a build failure.

    Parameters
    ----------
    llm_call : callable
        ``llm_call(prompt: str) -> str`` — single-turn LLM invocation.
    feature_name : str
        Name of the feature that failed.
    gate_failed : str
        Which gate failed (BUILD, EG2, EG3, EG4, EG5, MERGE).
    error_pattern : str
        The error text from the failed gate.
    agent_output : str
        The agent's output (used for context; truncated to last 3000 chars).

    Returns
    -------
    dict or None
        ``{cause, rule}`` on success, None on parse failure or exception.
    """
    gate_context = _GATE_REFLECTION_CONTEXT.get(gate_failed, "")
    prompt = _REFLECTION_PROMPT.format(
        feature_name=feature_name,
        gate_failed=gate_failed,
        error_pattern=(error_pattern or "")[:2000],
        agent_tail=(agent_output or "")[-3000:],
        gate_context=gate_context,
    )
    try:
        raw = llm_call(prompt)
        return _parse_reflection_response(raw)
    except Exception as exc:
        logger.warning("KG: reflection LLM call failed: %s", exc)
        return None


def _parse_reflection_response(response: str) -> dict | None:
    """Extract CAUSE/RULE from reflection LLM response."""
    cause = ""
    rule = ""
    for line in response.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("CAUSE:"):
            cause = stripped[len("CAUSE:"):].strip()
        elif stripped.upper().startswith("RULE:"):
            rule = stripped[len("RULE:"):].strip()
    if cause and rule:
        return {"cause": cause[:500], "rule": rule[:500]}
    return None


def capture_reflection(
    store: "KnowledgeStore | None",
    reflection: dict,
    feature_name: str,
    gate_failed: str,
    campaign_id: str | None = None,
) -> str | None:
    """Store a reflection result as an instance node in the KG.

    Returns the new node ID, or None if store is unavailable.
    The node starts at ``active`` — it must earn promotion via lift.
    """
    if store is None or reflection is None:
        return None
    try:
        node_id = store.add_node(
            node_type="instance",
            title=f"Reflection: {reflection['rule'][:150]}",
            content=(
                f"Root cause: {reflection['cause']}\n"
                f"Rule: {reflection['rule']}\n"
                f"Source: {gate_failed} failure on {feature_name}"
            ),
            campaign_id=campaign_id,
            status="active",
            metadata={
                "source": "structured_reflection",
                "gate_failed": gate_failed,
                "feature_name": feature_name,
                "cause": reflection["cause"],
                "rule": reflection["rule"],
            },
        )
        # Link to any matching universals
        store.link_to_universals(node_id)
        logger.info(
            "KG: captured reflection node %s from %s failure: %s",
            node_id, gate_failed, reflection["rule"][:80],
        )
        return node_id
    except Exception as exc:
        logger.warning("KG: capture_reflection failed: %s", exc)
        return None


def format_reflection_for_prompt(reflection: dict) -> str:
    """Format a reflection result for injection into a retry prompt.

    Returns a short markdown block suitable for appending to the user prompt.
    """
    return (
        f"\n\n## REFLECTION ON FAILURE\n"
        f"**Root cause:** {reflection['cause']}\n"
        f"**Rule:** {reflection['rule']}\n"
        f"Apply this rule in your next attempt.\n"
    )


# ── Cluster → Universal synthesis ────────────────────────────────────────────

# The other place LLM judgment is used.  Everything else is deterministic SQL.
# Created universals start at active and must earn promotion via lift > 0.

_SYNTHESIS_PROMPT = """\
You are distilling a reusable engineering rule from related build learnings.

Below are {count} related nodes from a knowledge graph.  They share these keywords: {keywords}.

{node_summaries}

Write a single universal engineering rule that captures the common pattern.
The rule must be:
- Actionable (starts with a verb: "Always...", "Never...", "Validate...")
- Domain-invariant (applies across projects, not specific to one feature)
- Concise (1-2 sentences max)

Respond with exactly two lines:
TITLE: <short rule title, max 120 chars>
CONTENT: <full rule text, max 500 chars>"""


def _build_synthesis_prompt(
    cluster: dict,
    store: "KnowledgeStore",
) -> str:
    """Build the one-shot prompt for a single cluster."""
    summaries: list[str] = []
    for nid in cluster["node_ids"]:
        node = store.get_node(nid)
        if node:
            title = node.get("title", "")
            content = (node.get("content") or "")[:300]
            summaries.append(f"- **{nid}** ({node['node_type']}): {title}\n  {content}")
    return _SYNTHESIS_PROMPT.format(
        count=cluster["size"],
        keywords=", ".join(cluster["shared_keywords"]),
        node_summaries="\n".join(summaries),
    )


def _parse_synthesis_response(response: str) -> tuple[str, str] | None:
    """Extract TITLE/CONTENT from LLM response.  Returns None on parse failure."""
    title = ""
    content = ""
    for line in response.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("TITLE:"):
            title = stripped[len("TITLE:"):].strip()
        elif stripped.upper().startswith("CONTENT:"):
            content = stripped[len("CONTENT:"):].strip()
    if title and content:
        return title[:200], content[:2000]
    return None


def synthesize_universals(
    store: "KnowledgeStore | None",
    llm_call: "callable",
    *,
    min_cluster_size: int = 3,
    max_synthesize: int = 5,
    campaign_id: str | None = None,
    dry_run: bool = False,
) -> list[dict]:
    """Find unlinked clusters and synthesize universal nodes via one-shot LLM.

    Parameters
    ----------
    store : KnowledgeStore or None
        The knowledge store.  No-op if None.
    llm_call : callable
        ``llm_call(prompt: str) -> str`` — single-turn LLM invocation.
        The caller owns model selection and API keys.  This function only
        provides the prompt and parses the response.
    min_cluster_size : int
        Minimum cluster members to trigger synthesis (default 3).
    max_synthesize : int
        Cap on universals created per sweep (default 5).
    campaign_id : str or None
        Campaign to tag new nodes with.
    dry_run : bool
        If True, return planned actions without creating nodes.

    Returns
    -------
    list[dict]
        Each entry: ``{node_id, title, member_ids, cluster}`` for created
        universals.  On dry_run, ``node_id`` is None.

    The created universals start at ``active`` — they must survive the
    injection → outcome → lift pipeline to promote.  Bad LLM output
    produces nodes that never promote (lift ≤ 0) and decay via recency.
    """
    if store is None:
        return []

    results: list[dict] = []
    try:
        clusters = store.find_generalization_clusters(min_cluster_size=min_cluster_size)
        for cluster in clusters[:max_synthesize]:
            prompt = _build_synthesis_prompt(cluster, store)

            if dry_run:
                results.append({
                    "node_id": None,
                    "title": cluster["suggested_title"],
                    "member_ids": cluster["node_ids"],
                    "cluster": cluster,
                    "prompt": prompt,
                })
                continue

            try:
                raw = llm_call(prompt)
                parsed = _parse_synthesis_response(raw)
                if parsed is None:
                    logger.warning(
                        "KG: synthesis LLM response unparseable for cluster %s, skipping",
                        cluster["shared_keywords"],
                    )
                    continue

                title, content = parsed
                node_id = store.materialize_cluster(
                    title=title,
                    content=content,
                    member_ids=cluster["node_ids"],
                    campaign_id=campaign_id,
                    source_cluster=cluster,
                )
                results.append({
                    "node_id": node_id,
                    "title": title,
                    "member_ids": cluster["node_ids"],
                    "cluster": cluster,
                })
                logger.info(
                    "KG: synthesized universal %s from %d members: %s",
                    node_id, cluster["size"], title,
                )
            except Exception as exc:
                logger.warning(
                    "KG: synthesis failed for cluster %s: %s",
                    cluster["shared_keywords"], exc,
                )
    except Exception as exc:
        logger.warning("KG: synthesize_universals sweep failed: %s", exc)

    return results
