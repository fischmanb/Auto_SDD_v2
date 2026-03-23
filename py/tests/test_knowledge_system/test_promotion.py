"""Tests for the promotion runner (auto_sdd_v2.knowledge_system.promotion)."""

import pytest

from auto_sdd_v2.knowledge_system.promotion import run_promotion
from auto_sdd_v2.knowledge_system.store import KnowledgeStore


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def store(db_path):
    s = KnowledgeStore(db_path)
    yield s
    s.close()


class TestRunPromotion:
    def test_empty_db_returns_zero_summary(self, db_path):
        summary = run_promotion(db_path)
        assert summary == {"promoted": 0, "hardened": 0, "demoted": 0, "total": 0}

    def test_promotes_eligible_node(self, db_path, store):
        store.add_node("instance", "T", "A", node_id="L-00001", stack="python")
        store.record_outcome("feat", 1, "success", node_ids_injected=["L-00001"])
        store.close()

        summary = run_promotion(db_path)

        assert summary["promoted"] == 1
        assert summary["total"] == 1

    def test_hardens_eligible_node(self, db_path, store):
        store.add_node("instance", "T", "A", node_id="L-00001", status="promoted")
        for i in range(3):
            store.record_outcome("feat", i + 1, "success", node_ids_injected=["L-00001"])
        store.close()

        summary = run_promotion(db_path)

        assert summary["hardened"] == 1
        assert summary["total"] == 1

    def test_demotes_eligible_hardened_node(self, db_path, store):
        store.add_node("instance", "T", "A", node_id="L-00001", status="hardened")
        # 1 success, 4 failures when injected (20%)
        store.record_outcome("feat", 1, "success", node_ids_injected=["L-00001"])
        for i in range(4):
            store.record_outcome("feat", i + 2, "failure", node_ids_injected=["L-00001"])
        # 5 successes in baseline (100%) → lift = -0.8 ≤ 0
        for i in range(5):
            store.record_outcome("other", i + 1, "success")
        store.close()

        summary = run_promotion(db_path)

        assert summary["demoted"] == 1
        assert summary["total"] == 1

    def test_no_changes_when_nothing_qualifies(self, db_path, store):
        # Active node but only failures — no promotions
        store.add_node("instance", "T", "A", node_id="L-00001", stack="python")
        store.record_outcome("feat", 1, "failure", node_ids_injected=["L-00001"])
        store.close()

        summary = run_promotion(db_path)

        assert summary == {"promoted": 0, "hardened": 0, "demoted": 0, "total": 0}

    def test_handles_bad_db_path_gracefully(self):
        # Non-existent parent dir — should NOT raise, returns zero summary with error flag
        # (SQLite will create the file, so we test with a genuinely bad path)
        summary = run_promotion("/dev/null/impossible/path/knowledge.db")
        assert summary["promoted"] == 0
        assert summary["hardened"] == 0
        assert summary["demoted"] == 0
        assert summary["total"] == 0
        assert summary.get("error") is True

    def test_idempotent_consecutive_runs(self, db_path, store):
        store.add_node("instance", "T", "A", node_id="L-00001", stack="python")
        store.record_outcome("feat", 1, "success", node_ids_injected=["L-00001"])
        store.close()

        summary1 = run_promotion(db_path)
        summary2 = run_promotion(db_path)

        assert summary1["promoted"] == 1
        assert summary2["total"] == 0  # Nothing new to promote
