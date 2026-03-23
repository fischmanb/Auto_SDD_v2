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
        store.add_node("instance", "A", "A", node_id="L-00001")
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

    def test_promoted_not_hardened_without_enough_campaigns(self, store):
        store.add_node("instance", "A", "A", node_id="L-00001", status="promoted")
        # 3 successes but only 1 campaign
        for i in range(3):
            store.record_outcome(
                "feature", i + 1, "success",
                campaign_id="c1",
                node_ids_injected=["L-00001"],
            )
        events = store.promote()
        assert not any(e.get("to") == "hardened" for e in events)

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
        store.add_node("instance", "A", "A", node_id="L-00001")
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
