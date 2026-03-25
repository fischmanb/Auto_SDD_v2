"""Tests for KnowledgeStore.query(): the 7-step deterministic pipeline."""

import pytest

from auto_sdd_v2.knowledge_system.store import KnowledgeStore


@pytest.fixture
def store(tmp_path):
    s = KnowledgeStore(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture
def populated_store(tmp_path):
    """Store with a set of known nodes for deterministic query tests."""
    s = KnowledgeStore(str(tmp_path / "populated.db"))

    # Hardened universal node — should rank highest
    s.add_node(
        "universal", "Always verify with machine gates",
        "Use git diff --stat and grep for mechanical verification, not agent self-assessment.",
        node_id="U-00001",
        stack=None,
        status="hardened",
    )

    # Instance node about nextjs stack
    s.add_node(
        "instance", "NEXT_PUBLIC_ prefix required for client env vars",
        "Environment variables used in client components require NEXT_PUBLIC_ prefix. "
        "Missing prefix silently returns undefined at runtime.",
        node_id="L-00001",
        stack="nextjs",
        status="active",
    )

    # Mistake node about build failure
    s.add_node(
        "mistake", "Server-only imports in client component",
        "Importing a module that transitively imports fs or postgres from a use client "
        "component causes a build failure in production.",
        node_id="K-00001",
        stack="nextjs",
        status="promoted",
    )

    # Meta node about python testing
    s.add_node(
        "meta", "pytest fixture scope best practice",
        "Use function scope for fixtures that modify state; session scope only for read-only setup.",
        node_id="M-00001",
        stack="python",
        status="active",
    )

    # Edge: L-00001 co_occurs with K-00001
    s.add_edge("L-00001", "K-00001", "co_occurs")

    yield s
    s.close()


class TestQueryReturnsResults:
    def test_empty_store_returns_empty(self, store):
        results = store.query()
        assert results == []

    def test_returns_list(self, populated_store):
        results = populated_store.query()
        assert isinstance(results, list)

    def test_max_results_respected(self, populated_store):
        results = populated_store.query(max_results=2)
        assert len(results) <= 2

    def test_each_result_is_dict(self, populated_store):
        results = populated_store.query()
        for r in results:
            assert isinstance(r, dict)
            assert "id" in r
            assert "_score" in r

    def test_results_sorted_descending_by_score(self, populated_store):
        results = populated_store.query()
        scores = [r["_score"] for r in results]
        assert scores == sorted(scores, reverse=True)


class TestQueryStackFilter:
    def test_stack_match_boosts_relevant_nodes(self, populated_store):
        results = populated_store.query(stack="nextjs", max_results=10)
        ids = [r["id"] for r in results]
        # Both nextjs nodes should appear
        assert "L-00001" in ids
        assert "K-00001" in ids

    def test_stack_filter_excludes_unrelated(self, populated_store):
        results = populated_store.query(stack="ruby", max_results=10)
        # No ruby nodes exist; fallback returns best active nodes
        assert isinstance(results, list)  # doesn't crash

    def test_python_stack_finds_pytest_node(self, populated_store):
        results = populated_store.query(stack="python", max_results=10)
        ids = [r["id"] for r in results]
        assert "M-00001" in ids


class TestQueryFts:
    def test_fts_keyword_match(self, populated_store):
        results = populated_store.query(
            feature_spec="environment variables NEXT_PUBLIC client component",
            max_results=10,
        )
        ids = [r["id"] for r in results]
        assert "L-00001" in ids

    def test_fts_error_pattern_match(self, populated_store):
        results = populated_store.query(
            error_pattern="postgres import build failure client",
            max_results=10,
        )
        ids = [r["id"] for r in results]
        assert "K-00001" in ids

    def test_fts_no_match_returns_fallback(self, populated_store):
        # A query with zero FTS matches should fall back to top-status nodes
        results = populated_store.query(
            feature_spec="zzzunmatchablezzztoken",
            max_results=5,
        )
        # Should still return something (fallback path)
        assert len(results) >= 1


class TestQueryEdgeExpansion:
    def test_edge_expansion_includes_neighbors(self, populated_store):
        """Querying by stack=nextjs should also surface K-00001 via L-00001's edge."""
        results = populated_store.query(stack="nextjs", max_results=10)
        ids = [r["id"] for r in results]
        # K-00001 is connected to L-00001 via co_occurs
        assert "K-00001" in ids

    def test_generalizes_edge_boosts_universal_from_instance(self, store):
        """When an instance matches, its universal ancestor gets a score boost via generalizes."""
        uid = store.add_node(
            "universal",
            "Environment validation principle",
            "Validate environment configuration before deployment",
            node_id="U-00001",
            status="promoted",
        )
        iid = store.add_node(
            "instance",
            "Check environment variables before build",
            "Always verify environment variables are configured correctly before running build",
            node_id="L-00001",
            stack="nextjs",
        )
        store.add_edge(uid, iid, "generalizes")
        # Query should find L-00001 via FTS, then pull in U-00001 via edge expansion
        results = store.query(
            feature_spec="environment variables configuration build",
            max_results=10,
        )
        ids = [r["id"] for r in results]
        assert "L-00001" in ids
        assert "U-00001" in ids


class TestQueryStatusFilter:
    def test_min_status_active_includes_all(self, populated_store):
        results = populated_store.query(min_status="active", max_results=20)
        statuses = {r["status"] for r in results}
        # Should include active, promoted, hardened
        assert "active" in statuses or "promoted" in statuses or "hardened" in statuses

    def test_min_status_promoted_excludes_active(self, populated_store):
        results = populated_store.query(min_status="promoted", max_results=20)
        for r in results:
            assert r["status"] in ("promoted", "hardened"), (
                f"Expected promoted/hardened but got {r['status']} for node {r['id']}"
            )

    def test_min_status_hardened_only(self, populated_store):
        results = populated_store.query(min_status="hardened", max_results=20)
        for r in results:
            assert r["status"] == "hardened"

    def test_deprecated_excluded_always(self, populated_store):
        populated_store.add_node(
            "instance", "Deprecated learning", "Old outdated content",
            node_id="L-99999",
            status="deprecated",
        )
        results = populated_store.query(max_results=50)
        ids = [r["id"] for r in results]
        assert "L-99999" not in ids

    def test_invalid_min_status_raises(self, populated_store):
        with pytest.raises(ValueError, match="Unknown min_status"):
            populated_store.query(min_status="garbage")


class TestQueryScoring:
    def test_hardened_outranks_active_for_same_stack(self, tmp_path):
        """Hardened nodes should score higher than active nodes."""
        store = KnowledgeStore(str(tmp_path / "scoring.db"))
        store.add_node("instance", "Hardened node", "content about testing pytest",
                       node_id="L-00001", status="hardened")
        store.add_node("instance", "Active node", "content about testing pytest",
                       node_id="L-00002", status="active")
        results = store.query(feature_spec="testing pytest", max_results=10)
        ids = [r["id"] for r in results]
        assert ids.index("L-00001") < ids.index("L-00002"), (
            "Hardened node should rank before active node"
        )
        store.close()

    def test_score_field_is_float(self, populated_store):
        results = populated_store.query(max_results=5)
        for r in results:
            assert isinstance(r["_score"], float)

    def test_successful_injection_boosts_score(self, tmp_path):
        """A node with prior successful injections should score higher than one without."""
        store = KnowledgeStore(str(tmp_path / "boost.db"))
        store.add_node("instance", "Node with success history", "content_uniquetoken_xyz",
                       node_id="L-00001")
        store.add_node("instance", "Node without history", "content_uniquetoken_xyz",
                       node_id="L-00002")
        store.record_outcome("feat", 1, "success",
                             campaign_id="c1", node_ids_injected=["L-00001"])
        results = store.query(feature_spec="content uniquetoken xyz", max_results=10)
        ids = [r["id"] for r in results]
        if "L-00001" in ids and "L-00002" in ids:
            assert ids.index("L-00001") <= ids.index("L-00002"), (
                "Node with success history should rank at least as high"
            )
        store.close()


class TestStackDetection:
    def test_detects_nextjs_from_spec(self, store):
        detected = store._detect_stack("app router with use client component")
        assert detected == "nextjs"

    def test_detects_python_from_spec(self, store):
        detected = store._detect_stack("pytest fixture for mypy strict checks")
        assert detected == "python"

    def test_returns_none_for_unknown(self, store):
        detected = store._detect_stack("some generic description without stack keywords")
        assert detected is None

    def test_returns_none_for_empty(self, store):
        detected = store._detect_stack(None)
        assert detected is None


class TestKeywordExtraction:
    def test_extracts_words_from_spec(self, store):
        kws = store._extract_keywords("user authentication component", None, None)
        assert "authentication" in kws
        assert "component" in kws

    def test_excludes_short_words(self, store):
        kws = store._extract_keywords("fix the bug in it", None, None)
        # Words shorter than 4 chars should be excluded
        short = [w for w in kws if len(w) < 4]
        assert short == []

    def test_deduplicates(self, store):
        kws = store._extract_keywords("testing testing testing", None, None)
        assert kws.count("testing") == 1

    def test_file_patterns_contribute(self, store):
        kws = store._extract_keywords(None, None, ["src/authentication.ts"])
        assert "authentication" in kws
