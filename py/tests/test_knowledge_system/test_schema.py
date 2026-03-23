"""Tests for knowledge_system.schema: table creation, FTS5, version tracking."""

import sqlite3
import tempfile
import os

import pytest

from auto_sdd_v2.knowledge_system.schema import (
    SCHEMA_VERSION,
    NODE_TYPES,
    EDGE_TYPES,
    STATUSES,
    STATUS_ORDER,
    init_db,
)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


class TestInitDb:
    def test_creates_file(self, db_path):
        conn = init_db(db_path)
        conn.close()
        assert os.path.isfile(db_path)

    def test_returns_connection(self, db_path):
        conn = init_db(db_path)
        assert conn is not None
        conn.close()

    def test_idempotent(self, db_path):
        """Calling init_db twice does not raise and returns valid connection."""
        conn1 = init_db(db_path)
        conn1.close()
        conn2 = init_db(db_path)
        conn2.close()

    def test_schema_version_recorded(self, db_path):
        conn = init_db(db_path)
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row[0] == SCHEMA_VERSION
        conn.close()

    def test_schema_version_not_duplicated_on_reinit(self, db_path):
        conn = init_db(db_path)
        conn.close()
        conn = init_db(db_path)
        count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
        assert count == 1
        conn.close()


class TestTables:
    def test_nodes_table_exists(self, db_path):
        conn = init_db(db_path)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='nodes'"
        ).fetchone()
        assert row is not None
        conn.close()

    def test_edges_table_exists(self, db_path):
        conn = init_db(db_path)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='edges'"
        ).fetchone()
        assert row is not None
        conn.close()

    def test_promotions_table_exists(self, db_path):
        conn = init_db(db_path)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='promotions'"
        ).fetchone()
        assert row is not None
        conn.close()

    def test_build_outcomes_table_exists(self, db_path):
        conn = init_db(db_path)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='build_outcomes'"
        ).fetchone()
        assert row is not None
        conn.close()

    def test_nodes_fts_virtual_table_exists(self, db_path):
        conn = init_db(db_path)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='nodes_fts'"
        ).fetchone()
        assert row is not None
        conn.close()


class TestFts5:
    def test_fts_insert_via_trigger(self, db_path):
        conn = init_db(db_path)
        conn.row_factory = sqlite3.Row
        now = "2024-01-01T00:00:00+00:00"
        conn.execute(
            "INSERT INTO nodes(id, node_type, title, content, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("L-00001", "instance", "Test title", "Test content about nextjs", now, now),
        )
        conn.commit()

        rows = conn.execute(
            "SELECT id FROM nodes_fts WHERE nodes_fts MATCH 'nextjs'"
        ).fetchall()
        ids = [r["id"] for r in rows]
        assert "L-00001" in ids
        conn.close()

    def test_fts_delete_via_trigger(self, db_path):
        conn = init_db(db_path)
        conn.row_factory = sqlite3.Row
        now = "2024-01-01T00:00:00+00:00"
        conn.execute(
            "INSERT INTO nodes(id, node_type, title, content, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("L-00001", "instance", "Test title", "unique_keyword_xyz", now, now),
        )
        conn.commit()

        # Verify it's indexed
        rows = conn.execute(
            "SELECT id FROM nodes_fts WHERE nodes_fts MATCH 'unique_keyword_xyz'"
        ).fetchall()
        assert len(rows) == 1

        # Delete the node
        conn.execute("DELETE FROM nodes WHERE id = 'L-00001'")
        conn.commit()

        # Should be gone from FTS
        rows = conn.execute(
            "SELECT id FROM nodes_fts WHERE nodes_fts MATCH 'unique_keyword_xyz'"
        ).fetchall()
        assert len(rows) == 0
        conn.close()

    def test_fts_update_via_trigger(self, db_path):
        conn = init_db(db_path)
        conn.row_factory = sqlite3.Row
        now = "2024-01-01T00:00:00+00:00"
        conn.execute(
            "INSERT INTO nodes(id, node_type, title, content, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("L-00001", "instance", "Before title", "old_unique_content_aaa", now, now),
        )
        conn.commit()

        # Update content
        conn.execute(
            "UPDATE nodes SET content = 'new_unique_content_bbb', updated_at = ? WHERE id = ?",
            (now, "L-00001"),
        )
        conn.commit()

        # Old content should not match
        rows = conn.execute(
            "SELECT id FROM nodes_fts WHERE nodes_fts MATCH 'old_unique_content_aaa'"
        ).fetchall()
        assert len(rows) == 0

        # New content should match
        rows = conn.execute(
            "SELECT id FROM nodes_fts WHERE nodes_fts MATCH 'new_unique_content_bbb'"
        ).fetchall()
        assert len(rows) == 1
        conn.close()


class TestConstants:
    def test_schema_version_is_positive_int(self):
        assert isinstance(SCHEMA_VERSION, int)
        assert SCHEMA_VERSION >= 1

    def test_node_types_includes_required(self):
        required = {"universal", "framework", "technology", "instance", "mistake", "meta"}
        assert required <= NODE_TYPES

    def test_edge_types_includes_required(self):
        required = {"generalizes", "contradicts", "supersedes", "co_occurs", "caused_by", "resolved_by"}
        assert required <= EDGE_TYPES

    def test_statuses_includes_required(self):
        required = {"active", "promoted", "hardened", "deprecated"}
        assert required <= STATUSES

    def test_status_order_monotone(self):
        # active < promoted < hardened
        assert STATUS_ORDER["active"] < STATUS_ORDER["promoted"] < STATUS_ORDER["hardened"]
        # deprecated is lowest (excluded tier)
        assert STATUS_ORDER["deprecated"] < STATUS_ORDER["active"]
