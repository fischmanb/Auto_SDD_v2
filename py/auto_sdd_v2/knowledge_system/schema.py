"""
SQLite schema for the knowledge system graph store.

Tables:
  nodes           — knowledge nodes (learnings, patterns, mistakes)
  edges           — directed relationships between nodes
  promotions      — promotion event log (active → promoted → hardened)
  build_outcomes  — per-build injection and outcome records
  schema_version  — migration version tracker

FTS:
  nodes_fts       — FTS5 full-text index on nodes.title + nodes.content
                    (independent table; kept in sync via triggers)
"""

import sqlite3
from datetime import datetime, timezone

SCHEMA_VERSION = 1

# Valid enum values — checked by application layer (SQLite CHECK constraints duplicate here)
NODE_TYPES = frozenset({"universal", "framework", "technology", "instance", "mistake", "meta"})
EDGE_TYPES = frozenset({"generalizes", "contradicts", "supersedes", "co_occurs", "caused_by", "resolved_by"})
STATUSES = frozenset({"active", "promoted", "hardened", "deprecated"})
OUTCOMES = frozenset({"success", "failure"})

# Status ordering for filtering (higher = more selective)
STATUS_ORDER = {"active": 0, "promoted": 1, "hardened": 2, "deprecated": -1}

_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    id          TEXT    PRIMARY KEY,
    node_type   TEXT    NOT NULL
                        CHECK(node_type IN ('universal','framework','technology','instance','mistake','meta')),
    title       TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    source_file TEXT,
    stack       TEXT,
    campaign_id TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    metadata    TEXT,
    embedding   BLOB,
    status      TEXT    NOT NULL DEFAULT 'active'
                        CHECK(status IN ('active','promoted','hardened','deprecated'))
);

CREATE TABLE IF NOT EXISTS edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   TEXT    NOT NULL REFERENCES nodes(id),
    target_id   TEXT    NOT NULL REFERENCES nodes(id),
    edge_type   TEXT    NOT NULL
                        CHECK(edge_type IN ('generalizes','contradicts','supersedes','co_occurs','caused_by','resolved_by')),
    weight      REAL    NOT NULL DEFAULT 1.0,
    context     TEXT,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS promotions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id      TEXT    NOT NULL REFERENCES nodes(id),
    from_status  TEXT    NOT NULL,
    to_status    TEXT    NOT NULL,
    rule_matched TEXT    NOT NULL,
    evidence     TEXT,
    promoted_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS build_outcomes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    feature_name      TEXT    NOT NULL,
    campaign_id       TEXT,
    node_ids_injected TEXT,
    attempt           INTEGER NOT NULL,
    outcome           TEXT    NOT NULL CHECK(outcome IN ('success','failure')),
    gate_failed       TEXT,
    error_pattern     TEXT,
    duration_seconds  REAL,
    recorded_at       TEXT    NOT NULL
);

-- FTS5 full-text index (independent; triggers keep it in sync)
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    id,
    title,
    content
);

-- Sync triggers
CREATE TRIGGER IF NOT EXISTS nodes_fts_ai
AFTER INSERT ON nodes BEGIN
    INSERT INTO nodes_fts(id, title, content)
    VALUES (new.id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS nodes_fts_ad
AFTER DELETE ON nodes BEGIN
    DELETE FROM nodes_fts WHERE id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS nodes_fts_au
AFTER UPDATE ON nodes BEGIN
    DELETE FROM nodes_fts WHERE id = old.id;
    INSERT INTO nodes_fts(id, title, content)
    VALUES (new.id, new.title, new.content);
END;

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_nodes_stack   ON nodes(stack);
CREATE INDEX IF NOT EXISTS idx_nodes_status  ON nodes(status);
CREATE INDEX IF NOT EXISTS idx_nodes_type    ON nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_edges_source  ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target  ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_node ON build_outcomes(node_ids_injected);
CREATE INDEX IF NOT EXISTS idx_outcomes_feat ON build_outcomes(feature_name);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(db_path: str) -> sqlite3.Connection:
    """
    Open (or create) the SQLite database at *db_path*, apply the schema if
    needed, and return an open connection.

    Idempotent: safe to call on an existing database.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Apply DDL (CREATE IF NOT EXISTS — safe to re-run)
    conn.executescript(_DDL)

    # Record schema version if not already present
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] if row and row[0] is not None else 0
    if current < SCHEMA_VERSION:
        conn.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, _now()),
        )
        conn.commit()

    return conn
