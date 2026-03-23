"""Tests for knowledge system build loop integration.

Covers:
- _kg_post_gate creates nodes on success and failure
- _build_user_prompt includes knowledge section when KG has relevant data
- _build_system_prompt includes hardened clues
- KG failure doesn't block build (graceful degradation)
- Token caps are respected
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auto_sdd_v2.knowledge_system.build_integration import (
    _CHARS_PER_TOKEN,
    _SPEC_PROMPT_MAX_TOKENS,
    _SYSTEM_PROMPT_MAX_TOKENS,
    _USER_PROMPT_MAX_TOKENS,
    detect_project_stack,
    extract_learning_candidates,
    inject_hardened_clues,
    inject_relevant_knowledge,
    inject_spec_learnings,
    init_store_optional,
    kg_post_gate,
)
from auto_sdd_v2.knowledge_system.store import KnowledgeStore


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    return str(tmp_path / "test.db")


@pytest.fixture
def store(tmp_db: str) -> KnowledgeStore:
    return KnowledgeStore(tmp_db)


@pytest.fixture
def store_with_nodes(store: KnowledgeStore) -> KnowledgeStore:
    """Store pre-populated with a mix of node types and statuses."""
    store.add_node(
        "instance",
        "Avoid relative imports",
        "Always use absolute imports from the package root.",
        stack="python",
        status="active",
    )
    store.add_node(
        "instance",
        "Next.js client boundary rule",
        "Do not import server-only modules from use-client components.",
        stack="nextjs",
        status="hardened",
    )
    store.add_node(
        "universal",
        "Token cap enforcement",
        "Hard cap injection to 2000 tokens for user prompt sections.",
        status="promoted",
    )
    return store


# ── init_store_optional ───────────────────────────────────────────────────────


def test_init_store_optional_creates_db(tmp_path: Path) -> None:
    db_path = str(tmp_path / "sub" / "knowledge.db")
    store = init_store_optional(db_path)
    assert store is not None
    assert os.path.isfile(db_path)
    store.close()


def test_init_store_optional_returns_none_on_bad_path() -> None:
    # KnowledgeStore is imported lazily inside init_store_optional, so we
    # patch it at its definition module rather than at the integration module.
    with patch(
        "auto_sdd_v2.knowledge_system.store.KnowledgeStore",
        side_effect=OSError("permission denied"),
    ):
        result = init_store_optional("/tmp/test_bad/knowledge.db")
    assert result is None


# ── detect_project_stack ──────────────────────────────────────────────────────


def test_detect_project_stack_nextjs(tmp_path: Path) -> None:
    (tmp_path / "next.config.js").write_text("")
    assert detect_project_stack(tmp_path) == "nextjs"


def test_detect_project_stack_react(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"dependencies": {"react": "18"}}')
    assert detect_project_stack(tmp_path) == "react"


def test_detect_project_stack_python(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'")
    assert detect_project_stack(tmp_path) == "python"


def test_detect_project_stack_unknown(tmp_path: Path) -> None:
    assert detect_project_stack(tmp_path) is None


# ── extract_learning_candidates ───────────────────────────────────────────────


def test_extract_learning_candidates_basic() -> None:
    output = (
        "some output\n"
        "LEARNING_CANDIDATE: Always use absolute imports\n"
        "more output\n"
        "LEARNING_CANDIDATE: Next.js requires NODE_ENV=production for build\n"
    )
    candidates = extract_learning_candidates(output)
    assert candidates == [
        "Always use absolute imports",
        "Next.js requires NODE_ENV=production for build",
    ]


def test_extract_learning_candidates_deduplicates() -> None:
    output = (
        "LEARNING_CANDIDATE: same thing\n"
        "LEARNING_CANDIDATE: same thing\n"
        "LEARNING_CANDIDATE: different thing\n"
    )
    candidates = extract_learning_candidates(output)
    assert candidates == ["same thing", "different thing"]


def test_extract_learning_candidates_empty() -> None:
    assert extract_learning_candidates("no signals here") == []


def test_extract_learning_candidates_strips_whitespace() -> None:
    output = "  LEARNING_CANDIDATE:   padded text   \n"
    candidates = extract_learning_candidates(output)
    assert candidates == ["padded text"]


# ── inject_relevant_knowledge ─────────────────────────────────────────────────


def test_inject_relevant_knowledge_returns_empty_for_none_store() -> None:
    section, ids = inject_relevant_knowledge(
        None, "some feature", stack="python"
    )
    assert section == ""
    assert ids == []


def test_inject_relevant_knowledge_returns_section_with_nodes(
    store_with_nodes: KnowledgeStore,
) -> None:
    section, ids = inject_relevant_knowledge(
        store_with_nodes,
        feature_spec="python imports configuration",
        stack="python",
    )
    assert section != ""
    assert "## Relevant Knowledge" in section
    assert len(ids) > 0


def test_inject_relevant_knowledge_respects_token_cap(
    store_with_nodes: KnowledgeStore,
) -> None:
    section, _ = inject_relevant_knowledge(
        store_with_nodes,
        feature_spec="feature spec content",
        stack=None,
        max_results=5,
    )
    max_chars = _USER_PROMPT_MAX_TOKENS * _CHARS_PER_TOKEN
    assert len(section) <= max_chars + len("\n[truncated to fit token budget]")


def test_inject_relevant_knowledge_error_pattern_for_retry(
    store_with_nodes: KnowledgeStore,
) -> None:
    """error_pattern is forwarded to query on retry attempts."""
    section, ids = inject_relevant_knowledge(
        store_with_nodes,
        feature_spec="feature",
        stack="python",
        error_pattern="import error absolute path",
    )
    # Should succeed (even if no match) without raising
    assert isinstance(section, str)
    assert isinstance(ids, list)


def test_inject_relevant_knowledge_handles_store_exception() -> None:
    bad_store = MagicMock()
    bad_store.query.side_effect = RuntimeError("db locked")
    section, ids = inject_relevant_knowledge(bad_store, "feature", stack=None)
    assert section == ""
    assert ids == []


# ── inject_hardened_clues ─────────────────────────────────────────────────────


def test_inject_hardened_clues_returns_empty_for_none_store() -> None:
    assert inject_hardened_clues(None, stack="python") == ""


def test_inject_hardened_clues_only_returns_hardened_nodes(
    store_with_nodes: KnowledgeStore,
) -> None:
    clues = inject_hardened_clues(store_with_nodes, stack="nextjs")
    # "active" node should not appear; only hardened (identified by its title)
    assert "HARDENED RULES" in clues
    assert "next.js client boundary rule" in clues.lower()


def test_inject_hardened_clues_empty_when_no_hardened_nodes(
    store: KnowledgeStore,
) -> None:
    store.add_node("instance", "Active only", "active content", status="active")
    clues = inject_hardened_clues(store, stack=None)
    assert clues == ""


def test_inject_hardened_clues_respects_token_cap(
    store_with_nodes: KnowledgeStore,
) -> None:
    clues = inject_hardened_clues(store_with_nodes, stack=None)
    max_chars = _SYSTEM_PROMPT_MAX_TOKENS * _CHARS_PER_TOKEN
    assert len(clues) <= max_chars + len("\n[truncated to fit token budget]")


def test_inject_hardened_clues_handles_store_exception() -> None:
    bad_store = MagicMock()
    bad_store.query.side_effect = RuntimeError("db locked")
    assert inject_hardened_clues(bad_store, stack=None) == ""


# ── inject_spec_learnings ─────────────────────────────────────────────────────


def test_inject_spec_learnings_returns_empty_for_none_store() -> None:
    assert inject_spec_learnings(None, stack="python") == ""


def test_inject_spec_learnings_returns_section(
    store_with_nodes: KnowledgeStore,
) -> None:
    section = inject_spec_learnings(store_with_nodes, stack=None)
    # At least one promoted+ node exists
    assert "## Project Learnings" in section


def test_inject_spec_learnings_respects_token_cap(
    store_with_nodes: KnowledgeStore,
) -> None:
    section = inject_spec_learnings(store_with_nodes, stack=None)
    max_chars = _SPEC_PROMPT_MAX_TOKENS * _CHARS_PER_TOKEN
    assert len(section) <= max_chars + len("\n[truncated to fit token budget]")


# ── kg_post_gate ──────────────────────────────────────────────────────────────


def test_kg_post_gate_records_success(store: KnowledgeStore) -> None:
    kg_post_gate(
        store,
        feature_name="Auth: Login",
        campaign_id="camp-001",
        injected_ids=[],
        attempt=0,
        outcome="success",
    )
    stats = store.stats()
    assert stats["outcomes"] == 1


def test_kg_post_gate_records_failure(store: KnowledgeStore) -> None:
    kg_post_gate(
        store,
        feature_name="Dashboard",
        campaign_id="camp-001",
        injected_ids=[],
        attempt=0,
        outcome="failure",
        gate_failed="EG4",
        error_pattern="Tests failed: 3 errors",
    )
    stats = store.stats()
    assert stats["outcomes"] == 1
    # Mistake node should be created
    assert stats["nodes"] == 1
    assert stats["by_type"].get("mistake", 0) == 1


def test_kg_post_gate_creates_mistake_node_only_with_error_pattern(
    store: KnowledgeStore,
) -> None:
    """No mistake node if error_pattern is absent even on failure."""
    kg_post_gate(
        store,
        feature_name="Dashboard",
        campaign_id="camp-001",
        injected_ids=[],
        attempt=0,
        outcome="failure",
        gate_failed="EG4",
        error_pattern=None,  # no pattern → no mistake node
    )
    stats = store.stats()
    assert stats["nodes"] == 0


def test_kg_post_gate_extracts_learning_candidates(store: KnowledgeStore) -> None:
    output = (
        "FEATURE_BUILT: Auth Login\n"
        "LEARNING_CANDIDATE: Always set NODE_ENV before running build\n"
    )
    kg_post_gate(
        store,
        feature_name="Auth: Login",
        campaign_id=None,
        injected_ids=[],
        attempt=0,
        outcome="success",
        agent_output=output,
    )
    stats = store.stats()
    assert stats["nodes"] == 1
    assert stats["by_type"].get("instance", 0) == 1


def test_kg_post_gate_noop_for_none_store() -> None:
    """Must not raise when store is None."""
    kg_post_gate(
        None,
        feature_name="Feature",
        campaign_id=None,
        injected_ids=[],
        attempt=0,
        outcome="success",
    )


def test_kg_post_gate_noop_on_exception() -> None:
    """Must not propagate exceptions — build must not be blocked."""
    bad_store = MagicMock()
    bad_store.record_outcome.side_effect = RuntimeError("unexpected")
    # Should not raise
    kg_post_gate(
        bad_store,
        feature_name="Feature",
        campaign_id=None,
        injected_ids=[],
        attempt=0,
        outcome="success",
    )


def test_kg_post_gate_records_injected_ids(store: KnowledgeStore) -> None:
    node_id = store.add_node(
        "instance",
        "A learning",
        "content",
        status="active",
        campaign_id="camp-001",
    )
    kg_post_gate(
        store,
        feature_name="Feature",
        campaign_id="camp-001",
        injected_ids=[node_id],
        attempt=0,
        outcome="success",
    )
    # Outcome row must reference the injected node
    row = store._conn.execute(
        "SELECT node_ids_injected FROM build_outcomes LIMIT 1"
    ).fetchone()
    assert row is not None
    import json
    assert node_id in json.loads(row[0])


def test_inject_spec_learnings_handles_store_exception() -> None:
    """Exception in store.query must not propagate — matches inject_hardened_clues pattern."""
    bad_store = MagicMock()
    bad_store.query.side_effect = RuntimeError("db locked")
    assert inject_spec_learnings(bad_store, stack=None) == ""


def test_kg_post_gate_no_mistake_node_when_gate_failed_is_none(
    store: KnowledgeStore,
) -> None:
    """gate_failed=None with error_pattern set → no mistake node created."""
    kg_post_gate(
        store,
        feature_name="Dashboard",
        campaign_id="camp-001",
        injected_ids=[],
        attempt=0,
        outcome="failure",
        gate_failed=None,
        error_pattern="something went wrong",
    )
    stats = store.stats()
    assert stats["nodes"] == 0


def test_kg_post_gate_both_mistake_and_instance_nodes(store: KnowledgeStore) -> None:
    """Failure with LEARNING_CANDIDATE creates both a mistake node and an instance node."""
    output = "LEARNING_CANDIDATE: Always check environment variables before build\n"
    kg_post_gate(
        store,
        feature_name="Auth: Login",
        campaign_id="camp-001",
        injected_ids=[],
        attempt=0,
        outcome="failure",
        gate_failed="EG4",
        error_pattern="Tests failed: 3 errors",
        agent_output=output,
    )
    stats = store.stats()
    assert stats["nodes"] == 2
    assert stats["by_type"].get("mistake", 0) == 1
    assert stats["by_type"].get("instance", 0) == 1


# ── Token cap with large content ──────────────────────────────────────────────


def test_truncate_applied_to_very_long_content(tmp_db: str) -> None:
    store = KnowledgeStore(tmp_db)
    # Insert a node with very long content
    long_content = "x" * (_USER_PROMPT_MAX_TOKENS * _CHARS_PER_TOKEN * 2)
    store.add_node(
        "universal",
        "Long learning",
        long_content,
        status="promoted",
    )
    section, _ = inject_relevant_knowledge(store, "feature", stack=None)
    max_chars = _USER_PROMPT_MAX_TOKENS * _CHARS_PER_TOKEN
    assert len(section) <= max_chars + len("\n[truncated to fit token budget]")
    store.close()
