"""Tests for KnowledgeStore: CRUD, edge operations, outcomes, stats."""

import json
import pytest

from auto_sdd_v2.knowledge_system.store import KnowledgeStore


@pytest.fixture
def store(tmp_path):
    s = KnowledgeStore(str(tmp_path / "test.db"))
    yield s
    s.close()


# ── Node CRUD ─────────────────────────────────────────────────────────────────

class TestAddNode:
    def test_add_returns_id(self, store):
        node_id = store.add_node("instance", "Test", "Some content")
        assert node_id.startswith("L-")

    def test_add_with_explicit_id(self, store):
        node_id = store.add_node("instance", "Title", "Body", node_id="L-00042")
        assert node_id == "L-00042"

    def test_auto_id_sequential(self, store):
        id1 = store.add_node("instance", "A", "Content A")
        id2 = store.add_node("instance", "B", "Content B")
        # IDs should be sequential
        n1 = int(id1.split("-")[1])
        n2 = int(id2.split("-")[1])
        assert n2 == n1 + 1

    def test_meta_prefix(self, store):
        node_id = store.add_node("meta", "Meta entry", "Content")
        assert node_id.startswith("M-")

    def test_mistake_prefix(self, store):
        node_id = store.add_node("mistake", "Mistake entry", "Content")
        assert node_id.startswith("K-")

    def test_universal_prefix(self, store):
        node_id = store.add_node("universal", "Universal entry", "Content")
        assert node_id.startswith("U-")

    def test_invalid_node_type_raises(self, store):
        with pytest.raises(ValueError, match="Unknown node_type"):
            store.add_node("bogus", "Title", "Content")

    def test_invalid_status_raises(self, store):
        with pytest.raises(ValueError, match="Unknown status"):
            store.add_node("instance", "Title", "Content", status="unknown_status")

    def test_stores_stack(self, store):
        store.add_node("instance", "Title", "Content", stack="nextjs")
        node = store.get_node("L-00001")
        assert node is not None
        assert node["stack"] == "nextjs"

    def test_stores_metadata_as_json(self, store):
        meta = {"tags": ["reliability"], "priority": 1}
        store.add_node("instance", "Title", "Content", metadata=meta)
        node = store.get_node("L-00001")
        assert node is not None
        parsed = json.loads(node["metadata"])
        assert parsed["tags"] == ["reliability"]


class TestGetNode:
    def test_returns_none_for_missing(self, store):
        result = store.get_node("L-99999")
        assert result is None

    def test_returns_dict(self, store):
        store.add_node("instance", "Title", "Body", node_id="L-00001")
        node = store.get_node("L-00001")
        assert isinstance(node, dict)
        assert node["id"] == "L-00001"
        assert node["title"] == "Title"
        assert node["content"] == "Body"

    def test_default_status_is_active(self, store):
        store.add_node("instance", "Title", "Body", node_id="L-00001")
        node = store.get_node("L-00001")
        assert node is not None
        assert node["status"] == "active"


class TestUpdateNodeStatus:
    def test_update_status(self, store):
        store.add_node("instance", "T", "C", node_id="L-00001")
        store.update_node_status("L-00001", "promoted")
        node = store.get_node("L-00001")
        assert node is not None
        assert node["status"] == "promoted"

    def test_invalid_status_raises(self, store):
        store.add_node("instance", "T", "C", node_id="L-00001")
        with pytest.raises(ValueError, match="Unknown status"):
            store.update_node_status("L-00001", "invalid")


# ── Edge operations ───────────────────────────────────────────────────────────

class TestAddEdge:
    def test_add_edge_returns_int(self, store):
        store.add_node("instance", "A", "Content A", node_id="L-00001")
        store.add_node("instance", "B", "Content B", node_id="L-00002")
        edge_id = store.add_edge("L-00001", "L-00002", "co_occurs")
        assert isinstance(edge_id, int)
        assert edge_id > 0

    def test_invalid_edge_type_raises(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        store.add_node("instance", "B", "B", node_id="L-00002")
        with pytest.raises(ValueError, match="Unknown edge_type"):
            store.add_edge("L-00001", "L-00002", "invalid_type")

    def test_all_valid_edge_types(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        store.add_node("instance", "B", "B", node_id="L-00002")
        valid_types = ["generalizes", "contradicts", "supersedes", "co_occurs", "caused_by", "resolved_by"]
        # Add all types between L-00001 and different dummy targets
        for i, etype in enumerate(valid_types, start=3):
            tid = f"L-000{i:02d}"
            store.add_node("instance", f"Node{i}", f"Content{i}", node_id=tid)
            edge_id = store.add_edge("L-00001", tid, etype)
            assert edge_id > 0

    def test_edge_with_context(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        store.add_node("instance", "B", "B", node_id="L-00002")
        ctx = {"error_pattern": "TypeError", "stack": "nextjs"}
        store.add_edge("L-00001", "L-00002", "caused_by", context=ctx)
        edges = store.get_edges("L-00001", direction="out")
        assert len(edges) == 1
        parsed_ctx = json.loads(edges[0]["context"])
        assert parsed_ctx["error_pattern"] == "TypeError"


class TestGetEdges:
    def test_outgoing_edges(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        store.add_node("instance", "B", "B", node_id="L-00002")
        store.add_node("instance", "C", "C", node_id="L-00003")
        store.add_edge("L-00001", "L-00002", "co_occurs")
        store.add_edge("L-00001", "L-00003", "generalizes")

        edges = store.get_edges("L-00001", direction="out")
        assert len(edges) == 2
        targets = {e["target_id"] for e in edges}
        assert targets == {"L-00002", "L-00003"}

    def test_incoming_edges(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        store.add_node("instance", "B", "B", node_id="L-00002")
        store.add_edge("L-00001", "L-00002", "co_occurs")

        edges = store.get_edges("L-00002", direction="in")
        assert len(edges) == 1
        assert edges[0]["source_id"] == "L-00001"

    def test_both_direction(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        store.add_node("instance", "B", "B", node_id="L-00002")
        store.add_node("instance", "C", "C", node_id="L-00003")
        store.add_edge("L-00001", "L-00002", "co_occurs")
        store.add_edge("L-00003", "L-00002", "co_occurs")

        edges = store.get_edges("L-00002", direction="both")
        assert len(edges) == 2

    def test_no_edges_returns_empty(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        assert store.get_edges("L-00001") == []


# ── Build outcomes ────────────────────────────────────────────────────────────

class TestRecordOutcome:
    def test_record_success(self, store):
        row_id = store.record_outcome(
            "auth-feature", 1, "success",
            campaign_id="camp-001",
            node_ids_injected=["L-00001"],
        )
        assert row_id > 0

    def test_record_failure(self, store):
        row_id = store.record_outcome(
            "auth-feature", 1, "failure",
            gate_failed="EG3",
            error_pattern="TypeError",
        )
        assert row_id > 0

    def test_invalid_outcome_raises(self, store):
        with pytest.raises(ValueError, match="Unknown outcome"):
            store.record_outcome("feature", 1, "unknown")

    def test_duration_stored(self, store):
        store.record_outcome("feature", 1, "success", duration=42.5)
        row = store._conn.execute(
            "SELECT duration_seconds FROM build_outcomes WHERE feature_name='feature'"
        ).fetchone()
        assert row[0] == pytest.approx(42.5)


# ── Stats ─────────────────────────────────────────────────────────────────────

class TestStats:
    def test_empty_store_stats(self, store):
        s = store.stats()
        assert s["nodes"] == 0
        assert s["edges"] == 0
        assert s["outcomes"] == 0
        assert s["promotions"] == 0

    def test_stats_count_nodes(self, store):
        store.add_node("instance", "A", "A")
        store.add_node("meta", "B", "B")
        s = store.stats()
        assert s["nodes"] == 2

    def test_stats_by_type(self, store):
        store.add_node("instance", "A", "A")
        store.add_node("instance", "B", "B")
        store.add_node("meta", "C", "C")
        s = store.stats()
        assert s["by_type"]["instance"] == 2
        assert s["by_type"]["meta"] == 1

    def test_stats_by_status(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        store.add_node("instance", "B", "B", node_id="L-00002", status="hardened")
        s = store.stats()
        assert s["by_status"]["active"] == 1
        assert s["by_status"]["hardened"] == 1

    def test_stats_count_edges(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        store.add_node("instance", "B", "B", node_id="L-00002")
        store.add_edge("L-00001", "L-00002", "co_occurs")
        s = store.stats()
        assert s["edges"] == 1


# ── Promotion ─────────────────────────────────────────────────────────────────

class TestPromote:
    def test_no_promotions_when_no_outcomes(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        events = store.promote()
        assert events == []

    def test_active_to_promoted_on_success(self, store):
        # Node with a stack satisfies the scope check
        store.add_node("instance", "A", "A", node_id="L-00001", stack="python")
        store.record_outcome(
            "feature", 1, "success",
            campaign_id="c1",
            node_ids_injected=["L-00001"],
        )
        events = store.promote()
        assert any(e["node_id"] == "L-00001" and e["to"] == "promoted" for e in events)
        node = store.get_node("L-00001")
        assert node is not None
        assert node["status"] == "promoted"

    def test_no_promotion_on_failure_only(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        store.record_outcome(
            "feature", 1, "failure",
            campaign_id="c1",
            node_ids_injected=["L-00001"],
        )
        events = store.promote()
        assert events == []
        node = store.get_node("L-00001")
        assert node is not None
        assert node["status"] == "active"

    def test_promoted_to_hardened(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001", status="promoted")
        # 3 successes across 2 campaigns
        for i in range(3):
            camp = "c1" if i < 2 else "c2"
            store.record_outcome(
                "feature", i + 1, "success",
                campaign_id=camp,
                node_ids_injected=["L-00001"],
            )
        events = store.promote()
        assert any(e["node_id"] == "L-00001" and e["to"] == "hardened" for e in events)
        node = store.get_node("L-00001")
        assert node is not None
        assert node["status"] == "hardened"

    def test_promoted_to_hardened_single_campaign(self, store):
        # Campaign diversity is no longer required — lift > 0 is the sole gate.
        # 3 successes from 1 campaign, no baseline → lift = 1.0 > 0 → hardens.
        store.add_node("instance", "A", "A", node_id="L-00001", status="promoted")
        for i in range(3):
            store.record_outcome(
                "feature", i + 1, "success",
                campaign_id="c1",
                node_ids_injected=["L-00001"],
            )
        events = store.promote()
        assert any(e["node_id"] == "L-00001" and e["to"] == "hardened" for e in events)
        node = store.get_node("L-00001")
        assert node is not None
        assert node["status"] == "hardened"

    def test_hardened_node_not_re_promoted(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001", status="hardened")
        store.record_outcome(
            "feature", 1, "success",
            campaign_id="c1",
            node_ids_injected=["L-00001"],
        )
        events = store.promote()
        assert events == []  # hardened is not in promotion candidates

    def test_promotion_recorded_in_promotions_table(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001", stack="python")
        store.record_outcome(
            "feature", 1, "success",
            campaign_id="c1",
            node_ids_injected=["L-00001"],
        )
        store.promote()
        count = store._conn.execute(
            "SELECT COUNT(*) FROM promotions WHERE node_id = 'L-00001'"
        ).fetchone()[0]
        assert count == 1


# ── Stage 3: calculate_lift ───────────────────────────────────────────────────


class TestCalculateLift:
    def test_zero_when_no_outcomes(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        assert store.calculate_lift("L-00001") == 0.0

    def test_equals_with_rate_when_no_baseline(self, store):
        # All 3 builds used L-00001 → baseline is empty → lift = with_rate = 1.0
        store.add_node("instance", "A", "A", node_id="L-00001")
        for i in range(3):
            store.record_outcome(
                "feat", i + 1, "success",
                node_ids_injected=["L-00001"],
            )
        lift = store.calculate_lift("L-00001")
        assert lift == pytest.approx(1.0)

    def test_positive_when_injected_beats_baseline(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        # 3 successes when injected (100%)
        for i in range(3):
            store.record_outcome("feat", i + 1, "success", node_ids_injected=["L-00001"])
        # 1 success, 1 failure without this node (50%)
        store.record_outcome("other-feat", 1, "success")
        store.record_outcome("other-feat", 2, "failure")
        lift = store.calculate_lift("L-00001")
        # with_rate=1.0, baseline_rate=0.5 → lift=0.5
        assert lift == pytest.approx(0.5)

    def test_negative_when_injected_underperforms_baseline(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        # 1 success, 3 failures when injected (25%)
        for i in range(3):
            store.record_outcome("feat", i + 1, "failure", node_ids_injected=["L-00001"])
        store.record_outcome("feat", 4, "success", node_ids_injected=["L-00001"])
        # 4 successes without this node (100%)
        for i in range(4):
            store.record_outcome("other-feat", i + 1, "success")
        lift = store.calculate_lift("L-00001")
        # with_rate=0.25, baseline_rate=1.0 → lift=-0.75
        assert lift == pytest.approx(-0.75)

    def test_zero_when_never_injected_but_outcomes_exist(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        store.record_outcome("other-feat", 1, "success")  # no node_ids_injected
        lift = store.calculate_lift("L-00001")
        assert lift == 0.0

    def test_deterministic_on_repeated_calls(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        store.record_outcome("feat", 1, "success", node_ids_injected=["L-00001"])
        store.record_outcome("other", 1, "failure")
        lift1 = store.calculate_lift("L-00001")
        lift2 = store.calculate_lift("L-00001")
        assert lift1 == lift2


# ── Stage 3: scope check (active → promoted) ─────────────────────────────────


class TestPromoteScopeCheck:
    def test_not_promoted_without_stack_and_short_content(self, store):
        # No stack, content < 20 chars — scope check fails
        store.add_node("instance", "T", "short", node_id="L-00001")
        store.record_outcome("feat", 1, "success", node_ids_injected=["L-00001"])
        events = store.promote()
        assert events == []
        node = store.get_node("L-00001")
        assert node is not None
        assert node["status"] == "active"

    def test_promoted_with_stack_regardless_of_content_length(self, store):
        # Stack present → scope check passes even with short content
        store.add_node("instance", "T", "x", node_id="L-00001", stack="python")
        store.record_outcome("feat", 1, "success", node_ids_injected=["L-00001"])
        events = store.promote()
        assert any(e["node_id"] == "L-00001" and e["to"] == "promoted" for e in events)

    def test_promoted_with_long_content_no_stack(self, store):
        # No stack but content >= 20 chars → scope check passes
        store.add_node(
            "instance", "Title", "This content is long enough to pass", node_id="L-00001"
        )
        store.record_outcome("feat", 1, "success", node_ids_injected=["L-00001"])
        events = store.promote()
        assert any(e["node_id"] == "L-00001" and e["to"] == "promoted" for e in events)


# ── Stage 3: demotion (hardened → promoted) ──────────────────────────────────


class TestPromoteDemotion:
    def _make_hardened(self, store: "KnowledgeStore") -> None:
        store.add_node("instance", "A", "A", node_id="L-00001", status="hardened")

    def test_hardened_demoted_when_lift_drops(self, store):
        self._make_hardened(store)
        # 1 success, 4 failures when injected (20%)
        store.record_outcome("feat", 1, "success", node_ids_injected=["L-00001"])
        for i in range(4):
            store.record_outcome("feat", i + 2, "failure", node_ids_injected=["L-00001"])
        # 5 successes in baseline (100%)
        for i in range(5):
            store.record_outcome("other", i + 1, "success")
        # lift = 0.2 - 1.0 = -0.8 ≤ 0, total = 5 ≥ 5 → demote
        events = store.promote()
        assert any(
            e["node_id"] == "L-00001" and e["from"] == "hardened" and e["to"] == "promoted"
            for e in events
        )
        node = store.get_node("L-00001")
        assert node is not None
        assert node["status"] == "promoted"

    def test_hardened_not_demoted_with_fewer_than_5_injections(self, store):
        self._make_hardened(store)
        # Only 4 builds with this node — threshold not met
        for i in range(4):
            store.record_outcome("feat", i + 1, "failure", node_ids_injected=["L-00001"])
        for i in range(4):
            store.record_outcome("other", i + 1, "success")
        events = store.promote()
        demotions = [e for e in events if e.get("from") == "hardened"]
        assert demotions == []
        node = store.get_node("L-00001")
        assert node is not None
        assert node["status"] == "hardened"

    def test_hardened_not_demoted_when_lift_positive(self, store):
        self._make_hardened(store)
        # 5 successes when injected (100%)
        for i in range(5):
            store.record_outcome("feat", i + 1, "success", node_ids_injected=["L-00001"])
        # 5 failures in baseline (0%)
        for i in range(5):
            store.record_outcome("other", i + 1, "failure")
        # lift = 1.0 - 0.0 = 1.0 > 0 → no demotion
        events = store.promote()
        demotions = [e for e in events if e.get("from") == "hardened"]
        assert demotions == []

    def test_demotion_recorded_in_promotions_table(self, store):
        self._make_hardened(store)
        for i in range(5):
            store.record_outcome("feat", i + 1, "failure", node_ids_injected=["L-00001"])
        for i in range(5):
            store.record_outcome("other", i + 1, "success")
        store.promote()
        rows = store._conn.execute(
            "SELECT * FROM promotions WHERE node_id='L-00001' AND to_status='promoted'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["from_status"] == "hardened"


# ── Stage 3: idempotency ──────────────────────────────────────────────────────


class TestPromoteIdempotency:
    def test_double_run_no_duplicate_events(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001", stack="python")
        store.record_outcome("feat", 1, "success", node_ids_injected=["L-00001"])
        events1 = store.promote()
        events2 = store.promote()
        assert len(events1) == 1
        assert len(events2) == 0  # Already promoted; no new events

    def test_already_promoted_stays_promoted(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001", stack="python")
        store.record_outcome("feat", 1, "success", node_ids_injected=["L-00001"])
        store.promote()
        node = store.get_node("L-00001")
        assert node is not None
        assert node["status"] == "promoted"
        store.promote()
        node = store.get_node("L-00001")
        assert node is not None
        assert node["status"] == "promoted"

    def test_hardened_stays_hardened_when_lift_positive(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001", status="promoted")
        for i in range(3):
            store.record_outcome("feat", i + 1, "success", node_ids_injected=["L-00001"])
        store.promote()
        store.promote()  # second run
        node = store.get_node("L-00001")
        assert node is not None
        assert node["status"] == "hardened"


# ── Stage 3: enhanced stats ───────────────────────────────────────────────────


class TestStatsEnhanced:
    def test_stats_includes_hardened_with_lift(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001", status="hardened")
        store.record_outcome("feat", 1, "success", node_ids_injected=["L-00001"])
        s = store.stats()
        assert "hardened_with_lift" in s
        assert isinstance(s["hardened_with_lift"], list)
        assert len(s["hardened_with_lift"]) == 1
        entry = s["hardened_with_lift"][0]
        assert entry["id"] == "L-00001"
        assert "lift" in entry

    def test_stats_includes_promotion_candidates(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001", status="promoted")
        for i in range(2):
            store.record_outcome("feat", i + 1, "success", node_ids_injected=["L-00001"])
        s = store.stats()
        assert "promotion_candidates" in s
        ids = [c["id"] for c in s["promotion_candidates"]]
        assert "L-00001" in ids

    def test_stats_promotion_pipeline_matches_by_status(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001", status="hardened")
        store.add_node("instance", "B", "B", node_id="L-00002", status="promoted")
        s = store.stats()
        assert s["promotion_pipeline"] == s["by_status"]

    def test_stats_empty_store(self, store):
        s = store.stats()
        assert s["hardened_with_lift"] == []
        assert s["promotion_candidates"] == []
        assert s["promotion_pipeline"] == {}
        assert s["generalization_clusters"] == []

    def test_stats_includes_generalization_clusters(self, store):
        for i in range(3):
            store.add_node(
                "instance",
                f"Import validation error case {i}",
                f"The import validation check failed because module resolution wrong #{i}",
                node_id=f"L-{i+1:05d}",
            )
        s = store.stats()
        assert "generalization_clusters" in s
        assert isinstance(s["generalization_clusters"], list)


# ── N-4: Boundary tests ───────────────────────────────────────────────────────


class TestPromoteBoundary:
    """Boundary conditions for promotion rules."""

    def test_promoted_not_hardened_when_lift_is_exactly_zero(self, store):
        # lift > 0 is required for hardening; lift = 0.0 exactly must NOT harden.
        store.add_node("instance", "A", "A", node_id="L-00001", status="promoted")
        # 3 successes when injected → with_rate = 1.0
        for i in range(3):
            store.record_outcome("feat", i + 1, "success", node_ids_injected=["L-00001"])
        # 3 successes without injection → baseline_rate = 1.0
        for i in range(3):
            store.record_outcome("base", i + 1, "success")
        # lift = 1.0 - 1.0 = 0.0 — not strictly > 0
        assert store.calculate_lift("L-00001") == 0.0
        events = store.promote()
        assert not any(e.get("to") == "hardened" for e in events)
        assert store.get_node("L-00001")["status"] == "promoted"  # type: ignore[index]

    def test_demotion_idempotent(self, store):
        # Calling promote() twice after demotion conditions are met leaves the
        # node at "promoted" on both the first and second run.
        store.add_node("instance", "A", "A", node_id="L-00001", status="hardened")
        # 5 failures injected + 5 successes baseline → lift = -1.0 ≤ 0 → demote
        for i in range(5):
            store.record_outcome("feat", i + 1, "failure", node_ids_injected=["L-00001"])
        for i in range(5):
            store.record_outcome("base", i + 1, "success")
        events1 = store.promote()
        assert any(
            e.get("from") == "hardened" and e.get("to") == "promoted" for e in events1
        )
        assert store.get_node("L-00001")["status"] == "promoted"  # type: ignore[index]
        # Second run: node is already "promoted"; demotion only applies to hardened nodes
        events2 = store.promote()
        assert not any(e.get("from") == "hardened" for e in events2)
        assert store.get_node("L-00001")["status"] == "promoted"  # type: ignore[index]

    def test_rehardens_after_demotion_when_lift_improves(self, store):
        # Re-hardening after demotion is intentional — the lift gate is authoritative.
        # A node that was hardened, demoted, then accumulates enough positive outcomes
        # will reharden on the next promotion run without any special case.
        store.add_node("instance", "A", "A", node_id="L-00001", status="hardened")
        # Phase 1: 5 failures injected + 10 successes baseline → lift = -1.0 → demote
        for i in range(5):
            store.record_outcome("feat1", i + 1, "failure", node_ids_injected=["L-00001"])
        for i in range(10):
            store.record_outcome("base1", i + 1, "success")
        events1 = store.promote()
        assert any(e.get("from") == "hardened" and e.get("to") == "promoted" for e in events1)
        assert store.get_node("L-00001")["status"] == "promoted"  # type: ignore[index]
        # Phase 2: 10 successes injected + 9 baseline failures
        #   with: 15 total, 10 success → rate ≈ 0.667
        #   baseline: 19 total, 10 success → rate ≈ 0.526
        #   lift ≈ 0.141 > 0, successes ≥ 3 → reharden
        for i in range(10):
            store.record_outcome("feat2", i + 1, "success", node_ids_injected=["L-00001"])
        for i in range(9):
            store.record_outcome("base2", i + 1, "failure")
        events2 = store.promote()
        assert any(e.get("to") == "hardened" for e in events2)
        assert store.get_node("L-00001")["status"] == "hardened"  # type: ignore[index]


# ── Generalization linking ───────────────────────────────────────────────────


class TestLinkToUniversals:
    def test_links_instance_to_matching_universal(self, store):
        store.add_node(
            "universal", "Respect client server boundaries",
            "Never import server-only modules from client components",
            node_id="U-00001",
        )
        instance_id = store.add_node(
            "instance", "Client component server import error",
            "Do not import server-only database modules from client components in Next.js",
        )
        linked = store.link_to_universals(instance_id)
        assert "U-00001" in linked
        # Edge direction: universal → instance
        edges = store.get_edges(instance_id, direction="in")
        gen_edges = [e for e in edges if e["edge_type"] == "generalizes"]
        assert len(gen_edges) == 1
        assert gen_edges[0]["source_id"] == "U-00001"

    def test_no_link_when_no_keyword_overlap(self, store):
        store.add_node(
            "universal", "Database indexing strategy",
            "Always add indexes for foreign key columns",
            node_id="U-00001",
        )
        instance_id = store.add_node(
            "instance", "CSS grid layout issue",
            "The flex container was overflowing on mobile viewport",
        )
        linked = store.link_to_universals(instance_id)
        assert linked == []

    def test_skips_deprecated_universals(self, store):
        store.add_node(
            "universal", "Import validation rules checking modules",
            "Always validate import paths and check module resolution",
            node_id="U-00001",
            status="deprecated",
        )
        instance_id = store.add_node(
            "instance", "Import validation failed for modules",
            "Module import validation check revealed broken paths",
        )
        linked = store.link_to_universals(instance_id)
        assert linked == []

    def test_does_not_self_link(self, store):
        uid = store.add_node(
            "universal", "Always validate inputs",
            "Input validation prevents injection attacks",
            node_id="U-00001",
        )
        linked = store.link_to_universals(uid)
        assert linked == []

    def test_idempotent_no_duplicate_edges(self, store):
        store.add_node(
            "universal", "Respect client server boundaries",
            "Never import server-only modules from client components",
            node_id="U-00001",
        )
        instance_id = store.add_node(
            "instance", "Client component server import error",
            "Do not import server-only database modules from client components",
        )
        linked1 = store.link_to_universals(instance_id)
        linked2 = store.link_to_universals(instance_id)
        assert len(linked1) >= 1
        assert linked2 == []  # Already linked

    def test_links_to_framework_and_technology_nodes(self, store):
        store.add_node(
            "framework", "Next.js server components pattern",
            "Server components should handle data fetching directly",
            node_id="U-00001",
        )
        store.add_node(
            "technology", "TypeScript strict mode checking",
            "Enable strict mode for better type checking safety",
            node_id="U-00002",
        )
        instance_id = store.add_node(
            "instance", "Server components data fetching issue",
            "Server components failed when data fetching was delegated to client",
        )
        linked = store.link_to_universals(instance_id)
        assert "U-00001" in linked

    def test_edge_weight_reflects_overlap_ratio(self, store):
        store.add_node(
            "universal", "Always validate input data",
            "Input validation prevents injection attacks and data corruption",
            node_id="U-00001",
        )
        instance_id = store.add_node(
            "instance", "Input validation missing on form",
            "The form submission lacked input validation causing data corruption",
        )
        store.link_to_universals(instance_id)
        edges = store.get_edges(instance_id, direction="in")
        gen_edges = [e for e in edges if e["edge_type"] == "generalizes"]
        assert len(gen_edges) == 1
        assert gen_edges[0]["weight"] > 0
        assert gen_edges[0]["weight"] <= 1.0

    def test_returns_empty_for_nonexistent_node(self, store):
        assert store.link_to_universals("L-99999") == []

    def test_case_insensitive_keyword_matching(self, store):
        """Keywords like 'VALIDATE' and 'validate' should match."""
        store.add_node(
            "universal", "VALIDATE Import Paths Always",
            "Always VALIDATE that IMPORT paths resolve correctly",
            node_id="U-00001",
        )
        instance_id = store.add_node(
            "instance", "validate import paths for modules",
            "Need to validate import paths before running the test suite",
        )
        linked = store.link_to_universals(instance_id)
        assert "U-00001" in linked


class TestFindGeneralizationClusters:
    def test_finds_cluster_of_similar_unlinked_nodes(self, store):
        # Three instance nodes about import validation — should cluster
        for i in range(3):
            store.add_node(
                "instance",
                f"Import validation error case {i}",
                f"The import validation check failed because module resolution was wrong #{i}",
                node_id=f"L-{i+1:05d}",
            )
        clusters = store.find_generalization_clusters(min_cluster_size=3)
        assert len(clusters) >= 1
        # All three nodes should be in at least one cluster
        all_clustered = set()
        for c in clusters:
            all_clustered.update(c["node_ids"])
        assert {"L-00001", "L-00002", "L-00003"} <= all_clustered

    def test_no_clusters_below_threshold(self, store):
        for i in range(2):
            store.add_node(
                "instance",
                f"Import validation error {i}",
                f"Import validation failed #{i}",
                node_id=f"L-{i+1:05d}",
            )
        clusters = store.find_generalization_clusters(min_cluster_size=3)
        assert clusters == []

    def test_excludes_already_linked_nodes(self, store):
        store.add_node(
            "universal", "Import validation rules",
            "Always validate import paths",
            node_id="U-00001",
        )
        for i in range(3):
            nid = store.add_node(
                "instance",
                f"Import validation error {i}",
                f"Import validation failed because module resolution was wrong #{i}",
                node_id=f"L-{i+1:05d}",
            )
            # Link all of them to the universal
            store.add_edge("U-00001", nid, "generalizes")
        clusters = store.find_generalization_clusters(min_cluster_size=3)
        # No clusters — all nodes are already linked
        assert clusters == []

    def test_excludes_deprecated_nodes(self, store):
        for i in range(3):
            store.add_node(
                "instance",
                f"Import validation error {i}",
                f"Import validation failed #{i}",
                node_id=f"L-{i+1:05d}",
                status="deprecated",
            )
        clusters = store.find_generalization_clusters(min_cluster_size=3)
        assert clusters == []

    def test_empty_store_returns_empty(self, store):
        assert store.find_generalization_clusters() == []

    def test_cluster_has_expected_fields(self, store):
        for i in range(3):
            store.add_node(
                "instance",
                f"Import validation error case {i}",
                f"Import validation check failed module resolution wrong #{i}",
                node_id=f"L-{i+1:05d}",
            )
        clusters = store.find_generalization_clusters(min_cluster_size=3)
        if clusters:
            c = clusters[0]
            assert "shared_keywords" in c
            assert "node_ids" in c
            assert "suggested_title" in c
            assert "size" in c
            assert len(c["shared_keywords"]) >= 2


class TestMaterializeCluster:
    def test_creates_universal_with_edges(self, store):
        for i in range(3):
            store.add_node(
                "instance", f"Node {i}", f"Content {i}",
                node_id=f"L-{i+1:05d}",
            )
        uid = store.materialize_cluster(
            title="Always validate imports",
            content="Validate import paths before committing code changes.",
            member_ids=["L-00001", "L-00002", "L-00003"],
        )
        assert uid.startswith("U-")
        node = store.get_node(uid)
        assert node is not None
        assert node["node_type"] == "universal"
        assert node["status"] == "active"  # must earn promotion
        # Check edges exist for all members
        for mid in ["L-00001", "L-00002", "L-00003"]:
            assert store.edge_exists(uid, mid, "generalizes")

    def test_metadata_tracks_source(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        cluster = {"shared_keywords": ["import", "validate"], "size": 1}
        uid = store.materialize_cluster(
            title="Rule",
            content="Content",
            member_ids=["L-00001"],
            source_cluster=cluster,
        )
        import json
        node = store.get_node(uid)
        assert node is not None
        meta = json.loads(node["metadata"])
        assert meta["source"] == "cluster_materialization"
        assert meta["member_ids"] == ["L-00001"]
        assert meta["cluster"] == cluster

    def test_skips_nonexistent_members(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001")
        uid = store.materialize_cluster(
            title="Rule",
            content="Content",
            member_ids=["L-00001", "L-99999"],  # L-99999 doesn't exist
        )
        # Should create edge only for existing member
        assert store.edge_exists(uid, "L-00001", "generalizes")
        assert not store.edge_exists(uid, "L-99999", "generalizes")

    def test_materialized_node_participates_in_promotion(self, store):
        """Materialized universals go through normal promotion pipeline."""
        store.add_node("instance", "A", "A", node_id="L-00001")
        uid = store.materialize_cluster(
            title="Validate everything",
            content="Always validate before proceeding.",
            member_ids=["L-00001"],
            stack="python",
        )
        # Starts active
        assert store.get_node(uid)["status"] == "active"
        # Simulate successful injection
        store.record_outcome(
            "feat", 1, "success",
            node_ids_injected=[uid],
            campaign_id="c1",
        )
        events = store.promote()
        assert any(e["node_id"] == uid and e["to"] == "promoted" for e in events)

    def test_materialized_node_excluded_from_clusters(self, store):
        """After materialization, members should no longer appear in clusters."""
        for i in range(3):
            store.add_node(
                "instance",
                f"Import validation error case {i}",
                f"The import validation check failed module resolution wrong #{i}",
                node_id=f"L-{i+1:05d}",
            )
        # Before materialization — should have clusters
        clusters_before = store.find_generalization_clusters(min_cluster_size=3)
        assert len(clusters_before) >= 1

        # Materialize
        store.materialize_cluster(
            title="Validate imports",
            content="Always validate import paths",
            member_ids=["L-00001", "L-00002", "L-00003"],
        )

        # After — members are now linked, should not cluster
        clusters_after = store.find_generalization_clusters(min_cluster_size=3)
        assert clusters_after == []
