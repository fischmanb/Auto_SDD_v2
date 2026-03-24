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
    _parse_reflection_response,
    _parse_synthesis_response,
    capture_reflection,
    detect_project_stack,
    extract_learning_candidates,
    format_reflection_for_prompt,
    inject_hardened_clues,
    inject_relevant_knowledge,
    inject_spec_learnings,
    init_store_optional,
    kg_post_gate,
    reflect_on_failure,
    synthesize_universals,
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


# ── kg_post_gate generalization linking ─────────────────────────────────────


def test_kg_post_gate_links_mistake_to_universal(store: KnowledgeStore) -> None:
    """Mistake nodes get linked to matching universals on creation."""
    store.add_node(
        "universal",
        "Always validate environment variables before build",
        "Check that required environment variables are set before starting builds",
        node_id="U-00001",
    )
    kg_post_gate(
        store,
        feature_name="Auth: Login",
        campaign_id="camp-001",
        injected_ids=[],
        attempt=0,
        outcome="failure",
        gate_failed="EG3",
        error_pattern="Build failed because environment variables were not validated before build start",
    )
    # Should have created a mistake node and linked it to U-00001
    stats = store.stats()
    assert stats["edges"] >= 1
    # Find the mistake node
    mistakes = [
        dict(r) for r in store._conn.execute(
            "SELECT id FROM nodes WHERE node_type='mistake'"
        ).fetchall()
    ]
    assert len(mistakes) == 1
    edges = store.get_edges(mistakes[0]["id"], direction="in")
    gen_edges = [e for e in edges if e["edge_type"] == "generalizes"]
    assert len(gen_edges) == 1
    assert gen_edges[0]["source_id"] == "U-00001"


def test_kg_post_gate_links_learning_candidate_to_universal(
    store: KnowledgeStore,
) -> None:
    """LEARNING_CANDIDATE instance nodes get linked to matching universals."""
    store.add_node(
        "universal",
        "Validate import paths and module resolution",
        "Always verify that import paths resolve correctly before committing",
        node_id="U-00001",
    )
    output = "LEARNING_CANDIDATE: Always validate import paths and verify module resolution before running tests\n"
    kg_post_gate(
        store,
        feature_name="Feature X",
        campaign_id="camp-001",
        injected_ids=[],
        attempt=0,
        outcome="success",
        agent_output=output,
    )
    # Instance node should exist and be linked to U-00001
    instances = [
        dict(r) for r in store._conn.execute(
            "SELECT id FROM nodes WHERE node_type='instance'"
        ).fetchall()
    ]
    assert len(instances) == 1
    edges = store.get_edges(instances[0]["id"], direction="in")
    gen_edges = [e for e in edges if e["edge_type"] == "generalizes"]
    assert len(gen_edges) >= 1


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


# ── synthesize_universals ────────────────────────────────────────────────────


def _make_cluster_store(store: KnowledgeStore) -> KnowledgeStore:
    """Populate store with 3 instance nodes that will cluster."""
    for i in range(3):
        store.add_node(
            "instance",
            f"Import validation error case {i}",
            f"The import validation check failed because module resolution was wrong #{i}",
            node_id=f"L-{i+1:05d}",
        )
    return store


def _fake_llm(prompt: str) -> str:
    return (
        "TITLE: Always validate import paths before committing\n"
        "CONTENT: Verify that all import paths resolve correctly to prevent "
        "build failures from broken module resolution."
    )


def test_synthesize_universals_creates_nodes(store: KnowledgeStore) -> None:
    _make_cluster_store(store)
    results = synthesize_universals(store, _fake_llm, min_cluster_size=3)
    assert len(results) >= 1
    r = results[0]
    assert r["node_id"] is not None
    assert r["node_id"].startswith("U-")
    # Verify the node exists and is active
    node = store.get_node(r["node_id"])
    assert node is not None
    assert node["status"] == "active"
    assert node["node_type"] == "universal"
    # Verify edges to members
    for mid in r["member_ids"]:
        assert store.edge_exists(r["node_id"], mid, "generalizes")


def test_synthesize_universals_dry_run(store: KnowledgeStore) -> None:
    _make_cluster_store(store)
    results = synthesize_universals(store, _fake_llm, min_cluster_size=3, dry_run=True)
    assert len(results) >= 1
    assert results[0]["node_id"] is None
    assert "prompt" in results[0]
    # No nodes created
    stats = store.stats()
    assert stats["by_type"].get("universal", 0) == 0


def test_synthesize_universals_noop_for_none_store() -> None:
    assert synthesize_universals(None, _fake_llm) == []


def test_synthesize_universals_handles_bad_llm_response(
    store: KnowledgeStore,
) -> None:
    _make_cluster_store(store)

    def bad_llm(prompt: str) -> str:
        return "I don't know what you want me to do."

    results = synthesize_universals(store, bad_llm, min_cluster_size=3)
    assert results == []  # unparseable → skipped
    assert store.stats()["by_type"].get("universal", 0) == 0


def test_synthesize_universals_handles_llm_exception(
    store: KnowledgeStore,
) -> None:
    _make_cluster_store(store)

    def exploding_llm(prompt: str) -> str:
        raise RuntimeError("API timeout")

    results = synthesize_universals(store, exploding_llm, min_cluster_size=3)
    assert results == []


def test_synthesize_universals_respects_max_cap(store: KnowledgeStore) -> None:
    # Create enough nodes for multiple clusters (different keyword groups)
    for i in range(3):
        store.add_node(
            "instance",
            f"Import validation error {i}",
            f"Import validation check failed module resolution wrong #{i}",
            node_id=f"L-{i+1:05d}",
        )
    results = synthesize_universals(store, _fake_llm, min_cluster_size=3, max_synthesize=1)
    assert len(results) <= 1


def test_synthesize_universals_created_node_trackable_via_lift(
    store: KnowledgeStore,
) -> None:
    """The synthesized universal participates in the lift pipeline."""
    _make_cluster_store(store)
    results = synthesize_universals(store, _fake_llm, min_cluster_size=3)
    uid = results[0]["node_id"]

    # Simulate 3 successful injections
    for i in range(3):
        store.record_outcome(
            f"feat{i}", 1, "success",
            node_ids_injected=[uid],
            campaign_id="c1",
        )
    # Baseline: some failures without this node
    for i in range(3):
        store.record_outcome(f"other{i}", 1, "failure")

    lift = store.calculate_lift(uid)
    assert lift > 0  # with_rate=1.0, baseline_rate=0.0 → lift=1.0

    # Should promote active → promoted → hardened
    events = store.promote()
    promoted = [e for e in events if e["node_id"] == uid]
    assert len(promoted) >= 1


def test_synthesize_universals_bad_node_decays(store: KnowledgeStore) -> None:
    """A bad synthesized universal gets negative lift and never promotes."""
    _make_cluster_store(store)
    results = synthesize_universals(store, _fake_llm, min_cluster_size=3)
    uid = results[0]["node_id"]

    # Simulate: injected builds all fail, baseline succeeds
    for i in range(3):
        store.record_outcome(
            f"feat{i}", 1, "failure",
            node_ids_injected=[uid],
        )
    for i in range(3):
        store.record_outcome(f"other{i}", 1, "success")

    lift = store.calculate_lift(uid)
    assert lift < 0  # negative lift

    events = store.promote()
    # Should NOT promote — still active with negative lift
    assert not any(e["node_id"] == uid and e["to"] == "promoted" for e in events)
    assert store.get_node(uid)["status"] == "active"


def test_parse_synthesis_response_valid() -> None:
    resp = "TITLE: Always validate imports\nCONTENT: Check all import paths resolve."
    result = _parse_synthesis_response(resp)
    assert result is not None
    assert result == ("Always validate imports", "Check all import paths resolve.")


def test_parse_synthesis_response_invalid() -> None:
    assert _parse_synthesis_response("just some text") is None
    assert _parse_synthesis_response("TITLE: only title") is None
    assert _parse_synthesis_response("CONTENT: only content") is None


def test_parse_synthesis_response_strips_whitespace() -> None:
    resp = "  TITLE:   Padded title  \n  CONTENT:  Padded content  "
    result = _parse_synthesis_response(resp)
    assert result == ("Padded title", "Padded content")


# ── Structured reflection ────────────────────────────────────────────────────


def _fake_reflection_llm(prompt: str) -> str:
    return (
        "CAUSE: The test file imported a module that doesn't exist yet.\n"
        "RULE: Always create module files before writing tests that import them."
    )


def test_reflect_on_failure_parses_response() -> None:
    result = reflect_on_failure(
        _fake_reflection_llm,
        feature_name="Auth: Login",
        gate_failed="EG4",
        error_pattern="ModuleNotFoundError: No module named 'auth'",
    )
    assert result is not None
    assert "cause" in result
    assert "rule" in result
    assert "module" in result["cause"].lower()


def test_reflect_on_failure_handles_bad_response() -> None:
    def bad_llm(prompt: str) -> str:
        return "I'm not sure what happened."

    result = reflect_on_failure(
        bad_llm,
        feature_name="Auth",
        gate_failed="EG4",
        error_pattern="error",
    )
    assert result is None


def test_reflect_on_failure_handles_exception() -> None:
    def exploding_llm(prompt: str) -> str:
        raise RuntimeError("API down")

    result = reflect_on_failure(
        exploding_llm,
        feature_name="Auth",
        gate_failed="EG4",
        error_pattern="error",
    )
    assert result is None


def test_parse_reflection_response_valid() -> None:
    resp = "CAUSE: Missing import\nRULE: Always check imports"
    result = _parse_reflection_response(resp)
    assert result == {"cause": "Missing import", "rule": "Always check imports"}


def test_parse_reflection_response_invalid() -> None:
    assert _parse_reflection_response("just text") is None
    assert _parse_reflection_response("CAUSE: only cause") is None
    assert _parse_reflection_response("RULE: only rule") is None


def test_capture_reflection_creates_node(store: KnowledgeStore) -> None:
    reflection = {"cause": "Missing import", "rule": "Always verify imports exist"}
    node_id = capture_reflection(
        store,
        reflection,
        feature_name="Auth: Login",
        gate_failed="EG4",
        campaign_id="camp-001",
    )
    assert node_id is not None
    node = store.get_node(node_id)
    assert node is not None
    assert node["node_type"] == "instance"
    assert node["status"] == "active"
    assert "Reflection:" in node["title"]
    assert "Always verify imports exist" in node["content"]


def test_capture_reflection_noop_for_none_store() -> None:
    result = capture_reflection(None, {"cause": "x", "rule": "y"}, "feat", "EG4")
    assert result is None


def test_capture_reflection_noop_for_none_reflection(
    store: KnowledgeStore,
) -> None:
    result = capture_reflection(store, None, "feat", "EG4")
    assert result is None


def test_capture_reflection_participates_in_promotion(
    store: KnowledgeStore,
) -> None:
    """Reflection nodes go through the normal promotion pipeline."""
    reflection = {"cause": "Missing init", "rule": "Always create __init__.py"}
    node_id = capture_reflection(
        store, reflection, feature_name="Auth", gate_failed="EG4",
    )
    assert store.get_node(node_id)["status"] == "active"

    # Simulate successful injection
    store.record_outcome("feat1", 1, "success", node_ids_injected=[node_id])
    events = store.promote()
    assert any(e["node_id"] == node_id and e["to"] == "promoted" for e in events)


def test_format_reflection_for_prompt() -> None:
    reflection = {"cause": "Missing module", "rule": "Always create files first"}
    text = format_reflection_for_prompt(reflection)
    assert "REFLECTION ON FAILURE" in text
    assert "Missing module" in text
    assert "Always create files first" in text


def test_full_reflection_to_injection_flow(store: KnowledgeStore) -> None:
    """End-to-end: reflect → capture → inject → outcome → promote."""
    # Step 1: Reflect
    reflection = reflect_on_failure(
        _fake_reflection_llm,
        feature_name="Dashboard",
        gate_failed="EG3",
        error_pattern="TypeError: undefined is not a function",
    )
    assert reflection is not None

    # Step 2: Capture
    node_id = capture_reflection(
        store, reflection, feature_name="Dashboard", gate_failed="EG3",
    )
    assert node_id is not None

    # Step 3: Format for injection
    prompt_section = format_reflection_for_prompt(reflection)
    assert len(prompt_section) > 0

    # Step 4: Simulate successful builds with this node injected
    for i in range(3):
        store.record_outcome(
            f"feat{i}", 1, "success",
            node_ids_injected=[node_id],
        )
    for i in range(3):
        store.record_outcome(f"other{i}", 1, "failure")

    # Step 5: Promote — should go all the way through
    events = store.promote()
    assert any(e["node_id"] == node_id for e in events)
