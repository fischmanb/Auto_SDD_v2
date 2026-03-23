"""
KnowledgeStore — primary interface to the knowledge system SQLite graph.

All query paths are deterministic SQL; no LLM judgment in this module.
"""

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from auto_sdd_v2.knowledge_system._utils import detect_stack as _detect_stack_fn
from auto_sdd_v2.knowledge_system.schema import (
    EDGE_TYPES,
    NODE_TYPES,
    OUTCOMES,
    STATUS_ORDER,
    STATUSES,
    init_db,
)

# ── Type priority weights for scoring ────────────────────────────────────────
_TYPE_WEIGHT: dict[str, float] = {
    "universal":   5.0,
    "framework":   4.0,
    "technology":  3.0,
    "mistake":     2.0,
    "instance":    1.0,
    "meta":        0.5,
}

# Status multiplier applied during scoring
_STATUS_WEIGHT: dict[str, float] = {
    "hardened":   3.0,
    "promoted":   2.0,
    "active":     1.0,
    "deprecated": 0.0,
}

# Recency decay: score *= RECENCY_BASE ** days_old
_RECENCY_BASE = 0.995


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_id(conn: sqlite3.Connection, prefix: str) -> str:
    """Generate next sequential ID for a given prefix (L, M, U, K, ...)."""
    like = f"{prefix}-%"
    row = conn.execute(
        "SELECT id FROM nodes WHERE id LIKE ? ORDER BY id DESC LIMIT 1",
        (like,),
    ).fetchone()
    if row is None:
        return f"{prefix}-00001"
    # Extract numeric part from last ID
    match = re.search(r"(\d+)$", row[0])
    if match:
        n = int(match.group(1)) + 1
    else:
        n = 1
    return f"{prefix}-{n:05d}"


def _id_prefix_for_type(node_type: str) -> str:
    mapping = {
        "universal":   "U",
        "framework":   "U",
        "technology":  "U",
        "instance":    "L",
        "mistake":     "K",
        "meta":        "M",
    }
    return mapping.get(node_type, "L")


def _days_since(iso_ts: str) -> float:
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        return max(0.0, delta.total_seconds() / 86400.0)
    except (ValueError, TypeError):
        return 0.0


class KnowledgeStore:
    """Graph-based knowledge store backed by SQLite."""

    def __init__(self, db_path: str) -> None:
        """Open (or create) the store at *db_path*."""
        self._db_path = db_path
        self._conn = init_db(db_path)  # row_factory set inside init_db

    def close(self) -> None:
        self._conn.close()

    # ── Node CRUD ─────────────────────────────────────────────────────────────

    def add_node(
        self,
        node_type: str,
        title: str,
        content: str,
        *,
        node_id: str | None = None,
        stack: str | None = None,
        campaign_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        source_file: str | None = None,
        status: str = "active",
    ) -> str:
        """
        Insert a new node and return its ID.

        If *node_id* is provided, it is used as-is (for migrations/imports).
        Otherwise a sequential ID is auto-generated from the node_type.
        """
        if node_type not in NODE_TYPES:
            raise ValueError(f"Unknown node_type: {node_type!r}. Must be one of {sorted(NODE_TYPES)}")
        if status not in STATUSES:
            raise ValueError(f"Unknown status: {status!r}")

        if node_id is None:
            prefix = _id_prefix_for_type(node_type)
            node_id = _next_id(self._conn, prefix)

        now = _now()
        self._conn.execute(
            """
            INSERT INTO nodes(id, node_type, title, content, source_file, stack,
                              campaign_id, created_at, updated_at, metadata, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                node_type,
                title,
                content,
                source_file,
                stack,
                campaign_id,
                now,
                now,
                json.dumps(metadata) if metadata else None,
                status,
            ),
        )
        self._conn.commit()
        return node_id

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Return a node by ID, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_node_status(self, node_id: str, status: str) -> None:
        """Update the status field of a node."""
        if status not in STATUSES:
            raise ValueError(f"Unknown status: {status!r}")
        self._conn.execute(
            "UPDATE nodes SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), node_id),
        )
        self._conn.commit()

    # ── Edge operations ───────────────────────────────────────────────────────

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        *,
        weight: float = 1.0,
        context: dict[str, Any] | None = None,
    ) -> int:
        """
        Insert a directed edge and return its row ID.

        Raises ValueError for unknown edge_type.
        Raises sqlite3.IntegrityError if source_id or target_id don't exist.
        """
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"Unknown edge_type: {edge_type!r}. Must be one of {sorted(EDGE_TYPES)}")

        cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO edges(source_id, target_id, edge_type, weight, context, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                target_id,
                edge_type,
                weight,
                json.dumps(context) if context else None,
                _now(),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_edges(
        self,
        node_id: str,
        direction: str = "both",
    ) -> list[dict[str, Any]]:
        """
        Return edges connected to *node_id*.

        direction: 'out' (source), 'in' (target), 'both'
        """
        if direction == "out":
            rows = self._conn.execute(
                "SELECT * FROM edges WHERE source_id = ?", (node_id,)
            ).fetchall()
        elif direction == "in":
            rows = self._conn.execute(
                "SELECT * FROM edges WHERE target_id = ?", (node_id,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM edges WHERE source_id = ? OR target_id = ?",
                (node_id, node_id),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Build outcomes ────────────────────────────────────────────────────────

    def record_outcome(
        self,
        feature_name: str,
        attempt: int,
        outcome: str,
        *,
        campaign_id: str | None = None,
        node_ids_injected: list[str] | None = None,
        gate_failed: str | None = None,
        error_pattern: str | None = None,
        duration: float | None = None,
    ) -> int:
        """Record a build outcome and return its row ID."""
        if outcome not in OUTCOMES:
            raise ValueError(f"Unknown outcome: {outcome!r}. Must be 'success' or 'failure'")

        cursor = self._conn.execute(
            """
            INSERT INTO build_outcomes(feature_name, campaign_id, node_ids_injected,
                                       attempt, outcome, gate_failed, error_pattern,
                                       duration_seconds, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feature_name,
                campaign_id,
                json.dumps(node_ids_injected) if node_ids_injected else None,
                attempt,
                outcome,
                gate_failed,
                error_pattern,
                duration,
                _now(),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    # ── Query pipeline ────────────────────────────────────────────────────────

    def query(
        self,
        *,
        stack: str | None = None,
        feature_spec: str | None = None,
        error_pattern: str | None = None,
        file_patterns: list[str] | None = None,
        max_results: int = 5,
        min_status: str = "active",
    ) -> list[dict[str, Any]]:
        """
        7-step deterministic query pipeline. Returns up to *max_results* nodes,
        ranked by composite score.

        Steps:
          1. Parse context — derive FTS keywords and stack hint from inputs
          2. Stack match — exact SQL filter on nodes.stack
          3. FTS search — full-text match on nodes_fts
          4. Edge expansion — follow edges from matched nodes (depth 1)
          5. Score — edge_weight × recency × type_priority × status_weight
                    × historical_success_ratio
          6. Status filter — exclude nodes below *min_status* tier
          7. Deduplicate, sort, return top-K
        """
        if min_status not in STATUS_ORDER:
            raise ValueError(f"Unknown min_status: {min_status!r}")

        min_tier = STATUS_ORDER[min_status]

        # Step 1: Parse context
        keywords = self._extract_keywords(feature_spec, error_pattern, file_patterns)
        effective_stack = stack or self._detect_stack(feature_spec)

        # Collect candidate node IDs with initial scores
        candidates: dict[str, float] = {}  # id → raw score

        # Step 2: Stack match (exact)
        if effective_stack:
            rows = self._conn.execute(
                "SELECT id, node_type, status FROM nodes WHERE stack = ? AND status != 'deprecated'",
                (effective_stack,),
            ).fetchall()
            for row in rows:
                candidates[row["id"]] = candidates.get(row["id"], 0.0) + 2.0

        # Step 3: FTS search
        if keywords:
            fts_query = " OR ".join(
                f'"{kw}"' if " " in kw else kw
                for kw in keywords[:10]  # SQLite FTS5 query limit sanity
            )
            try:
                fts_rows = self._conn.execute(
                    "SELECT id FROM nodes_fts WHERE nodes_fts MATCH ?",
                    (fts_query,),
                ).fetchall()
                for row in fts_rows:
                    candidates[row["id"]] = candidates.get(row["id"], 0.0) + 3.0
            except sqlite3.OperationalError:
                # Malformed FTS query — fall back to LIKE search
                for kw in keywords[:5]:
                    like_rows = self._conn.execute(
                        "SELECT id FROM nodes WHERE title LIKE ? OR content LIKE ?",
                        (f"%{kw}%", f"%{kw}%"),
                    ).fetchall()
                    for row in like_rows:
                        candidates[row["id"]] = candidates.get(row["id"], 0.0) + 1.0

        # If no candidates yet, pull top active nodes by status tier
        if not candidates:
            fallback_rows = self._conn.execute(
                """
                SELECT id FROM nodes
                WHERE status != 'deprecated'
                ORDER BY
                    CASE status WHEN 'hardened' THEN 3 WHEN 'promoted' THEN 2 ELSE 1 END DESC,
                    created_at DESC
                LIMIT ?
                """,
                (max_results * 3,),
            ).fetchall()
            for row in fallback_rows:
                candidates[row["id"]] = 0.5

        # Step 4: Edge expansion (depth 1) — add connected nodes with partial score
        seed_ids = list(candidates.keys())
        if seed_ids:
            placeholders = ",".join("?" * len(seed_ids))
            edge_rows = self._conn.execute(
                f"""
                SELECT source_id, target_id, weight FROM edges
                WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})
                """,
                seed_ids + seed_ids,
            ).fetchall()
            for erow in edge_rows:
                for neighbor_id in (erow["source_id"], erow["target_id"]):
                    if neighbor_id not in candidates:
                        candidates[neighbor_id] = 0.0
                    candidates[neighbor_id] += erow["weight"] * 0.5

        # Step 5: Score — fetch node metadata and apply weights
        all_ids = list(candidates.keys())
        if not all_ids:
            return []

        placeholders = ",".join("?" * len(all_ids))
        node_rows = self._conn.execute(
            f"SELECT * FROM nodes WHERE id IN ({placeholders})",
            all_ids,
        ).fetchall()

        # Build success ratio cache from build_outcomes
        success_ratios = self._compute_success_ratios(all_ids)

        scored: list[tuple[float, dict[str, Any]]] = []
        for nrow in node_rows:
            node = dict(nrow)
            node_id = node["id"]

            # Status filter (Step 6 — skip deprecated and below-min-tier nodes)
            node_tier = STATUS_ORDER.get(node["status"], -1)
            if node_tier < 0 or node_tier < min_tier:
                continue

            base = candidates.get(node_id, 0.0)

            # Type priority
            type_w = _TYPE_WEIGHT.get(node["node_type"], 1.0)

            # Status multiplier
            status_w = _STATUS_WEIGHT.get(node["status"], 1.0)

            # Recency decay
            days = _days_since(node["created_at"])
            recency_w = _RECENCY_BASE ** days

            # Historical success ratio
            success_w = 1.0 + success_ratios.get(node_id, 0.0)

            final_score = base * type_w * status_w * recency_w * success_w
            scored.append((final_score, node))

        # Step 7: Sort descending, deduplicate (already unique by node_id), return top-K
        scored.sort(key=lambda t: t[0], reverse=True)
        results = []
        for score, node in scored[:max_results]:
            node["_score"] = round(score, 6)
            results.append(node)

        return results

    # ── Promotion engine ──────────────────────────────────────────────────────

    def promote(self) -> list[dict[str, Any]]:
        """
        Run promotion rules and return a list of promotion event records.
        Idempotent: running twice produces the same result.

        Rules:
          active   → promoted : ≥1 successful injection + well-defined scope
                                (scope: stack is not None OR content length ≥ 20)
          promoted → hardened : ≥3 successful injections + lift > 0
          hardened → promoted : ≥5 total injections + lift ≤ 0  (demotion)
        """
        events: list[dict[str, Any]] = []

        # Promotion candidates (active and promoted nodes)
        promotable = self._conn.execute(
            "SELECT id, status, stack, content FROM nodes WHERE status IN ('active', 'promoted')"
        ).fetchall()

        for node_row in promotable:
            node_id = node_row["id"]
            current_status = node_row["status"]
            stack = node_row["stack"]
            content = node_row["content"] or ""

            stats = self._outcome_stats(node_id)
            total = stats["total"]
            successes = stats["successes"]

            if total == 0:
                continue

            if current_status == "active" and successes >= 1:
                # Scope check: stack known OR content is substantive (≥ 20 chars)
                scope_ok = (stack is not None) or (len(content.strip()) >= 20)
                if scope_ok:
                    self._apply_promotion(
                        node_id,
                        from_status="active",
                        to_status="promoted",
                        rule="active→promoted: ≥1 successful injection, scope well-defined",
                        evidence=stats,
                    )
                    events.append({"node_id": node_id, "from": "active", "to": "promoted"})

            elif current_status == "promoted" and successes >= 3:
                lift = self.calculate_lift(node_id)
                if lift > 0:
                    self._apply_promotion(
                        node_id,
                        from_status="promoted",
                        to_status="hardened",
                        rule=f"promoted→hardened: ≥3 successes, lift={lift:.4f}",
                        evidence={**stats, "lift": lift},
                    )
                    events.append(
                        {"node_id": node_id, "from": "promoted", "to": "hardened", "lift": lift}
                    )

        # Demotion: hardened → promoted when lift ≤ 0 after ≥5 injections.
        # Re-hardening after demotion is intentional — the lift gate is authoritative.
        # If a demoted node accumulates enough successful injections to push lift > 0
        # again, it will reharden on the next promotion run without any special case.
        hardened_nodes = self._conn.execute(
            "SELECT id FROM nodes WHERE status = 'hardened'"
        ).fetchall()

        for node_row in hardened_nodes:
            node_id = node_row["id"]
            stats = self._outcome_stats(node_id)
            if stats["total"] < 5:
                continue
            lift = self.calculate_lift(node_id)
            if lift <= 0:
                self._apply_promotion(
                    node_id,
                    from_status="hardened",
                    to_status="promoted",
                    rule=f"hardened→promoted (demotion): ≥5 injections, lift={lift:.4f}",
                    evidence={**stats, "lift": lift},
                )
                events.append(
                    {"node_id": node_id, "from": "hardened", "to": "promoted", "lift": lift}
                )

        return events

    def calculate_lift(self, node_id: str) -> float:
        """Calculate success rate lift when this node was injected vs baseline.

        lift = with_rate - baseline_rate

        where:
          with_rate     = success rate across builds where node_id was injected
          baseline_rate = success rate across builds where node_id was NOT injected

        Returns 0.0 if no outcomes exist with this node injected.
        When no baseline builds exist (all recorded builds used this node),
        baseline_rate is treated as 0.0 so lift equals with_rate.

        Deterministic pure SQL arithmetic — no LLM judgment.
        """
        # Use json_each() for exact element membership — avoids substring collision
        # when IDs share a prefix (e.g. L-00001 vs L-000010).

        # Success rate when node was injected
        with_row = self._conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes
            FROM build_outcomes
            WHERE EXISTS (
                SELECT 1 FROM json_each(node_ids_injected) WHERE value = ?
            )
            """,
            (node_id,),
        ).fetchone()

        with_total = with_row["total"] or 0
        with_successes = int(with_row["successes"] or 0)

        if with_total == 0:
            return 0.0

        with_rate = with_successes / with_total

        # Baseline: all outcomes where this node was NOT injected
        baseline_row = self._conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes
            FROM build_outcomes
            WHERE node_ids_injected IS NULL
               OR NOT EXISTS (
                   SELECT 1 FROM json_each(node_ids_injected) WHERE value = ?
               )
            """,
            (node_id,),
        ).fetchone()

        baseline_total = baseline_row["total"] or 0
        baseline_successes = int(baseline_row["successes"] or 0)

        if baseline_total == 0:
            # No baseline builds — return with_rate (baseline treated as 0.0)
            return with_rate

        baseline_rate = baseline_successes / baseline_total
        return with_rate - baseline_rate

    def _apply_promotion(
        self,
        node_id: str,
        from_status: str,
        to_status: str,
        rule: str,
        evidence: dict[str, Any],
    ) -> None:
        now = _now()
        self._conn.execute(
            "UPDATE nodes SET status = ?, updated_at = ? WHERE id = ?",
            (to_status, now, node_id),
        )
        self._conn.execute(
            """
            INSERT INTO promotions(node_id, from_status, to_status, rule_matched, evidence, promoted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (node_id, from_status, to_status, rule, json.dumps(evidence), now),
        )
        self._conn.commit()

    def _outcome_stats(self, node_id: str) -> dict[str, Any]:
        """Compute success/failure stats for a node across all recorded outcomes.

        Uses json_each() for exact element membership — avoids substring collision
        when IDs share a prefix (e.g. L-00001 vs L-000010).
        """
        counts_row = self._conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes
            FROM build_outcomes
            WHERE EXISTS (
                SELECT 1 FROM json_each(node_ids_injected) WHERE value = ?
            )
            """,
            (node_id,),
        ).fetchone()

        total = counts_row["total"] or 0
        successes = int(counts_row["successes"] or 0)

        campaigns_rows = self._conn.execute(
            """
            SELECT DISTINCT campaign_id
            FROM build_outcomes
            WHERE EXISTS (
                SELECT 1 FROM json_each(node_ids_injected) WHERE value = ?
            )
              AND outcome = 'success'
              AND campaign_id IS NOT NULL
            """,
            (node_id,),
        ).fetchall()
        distinct_campaigns = len(campaigns_rows)

        return {
            "total": total,
            "successes": successes,
            "failures": total - successes,
            "distinct_campaigns": distinct_campaigns,
        }

    def _compute_success_ratios(self, node_ids: list[str]) -> dict[str, float]:
        """Return a node_id → success_ratio mapping for scoring."""
        if not node_ids:
            return {}
        ratios: dict[str, float] = {}
        for node_id in node_ids:
            stats = self._outcome_stats(node_id)
            if stats["total"] > 0:
                ratios[node_id] = stats["successes"] / stats["total"]
        return ratios

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return graph statistics for diagnostics and health checks.

        Includes:
          - node/edge/outcome/promotion counts
          - by_status / by_type breakdowns
          - promotion_pipeline: alias of by_status for clarity
          - promotion_candidates: promoted nodes close to hardening threshold
          - hardened_with_lift: hardened nodes with their measured lift scores
        """
        node_count = self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        outcome_count = self._conn.execute("SELECT COUNT(*) FROM build_outcomes").fetchone()[0]
        promotion_count = self._conn.execute("SELECT COUNT(*) FROM promotions").fetchone()[0]

        by_status: dict[str, int] = {}
        for row in self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM nodes GROUP BY status"
        ).fetchall():
            by_status[row["status"]] = row["cnt"]

        by_type: dict[str, int] = {}
        for row in self._conn.execute(
            "SELECT node_type, COUNT(*) as cnt FROM nodes GROUP BY node_type"
        ).fetchall():
            by_type[row["node_type"]] = row["cnt"]

        # Promotion candidates: promoted nodes with ≥2 successes (1 away from threshold)
        promoted_rows = self._conn.execute(
            "SELECT id, title FROM nodes WHERE status = 'promoted'"
        ).fetchall()
        promotion_candidates: list[dict[str, Any]] = []
        for prow in promoted_rows:
            pstats = self._outcome_stats(prow["id"])
            if pstats["successes"] >= 2:
                lift = self.calculate_lift(prow["id"])
                promotion_candidates.append({
                    "id": prow["id"],
                    "title": (prow["title"] or "")[:100],
                    "successes": pstats["successes"],
                    "lift": round(lift, 4),
                })
        promotion_candidates.sort(
            key=lambda x: (x["successes"], x["lift"]), reverse=True
        )

        # Hardened nodes with lift scores
        hardened_rows = self._conn.execute(
            "SELECT id, title FROM nodes WHERE status = 'hardened'"
        ).fetchall()
        hardened_with_lift: list[dict[str, Any]] = []
        for hrow in hardened_rows:
            lift = self.calculate_lift(hrow["id"])
            hardened_with_lift.append({
                "id": hrow["id"],
                "title": (hrow["title"] or "")[:100],
                "lift": round(lift, 4),
            })
        hardened_with_lift.sort(key=lambda x: x["lift"], reverse=True)

        return {
            "nodes": node_count,
            "edges": edge_count,
            "outcomes": outcome_count,
            "promotions": promotion_count,
            "by_status": by_status,
            "by_type": by_type,
            "promotion_pipeline": dict(by_status),
            "promotion_candidates": promotion_candidates,
            "hardened_with_lift": hardened_with_lift,
        }

    # ── Public migration helpers ──────────────────────────────────────────────

    def get_all_node_ids(self) -> set[str]:
        """Return the set of all node IDs currently in the store."""
        rows = self._conn.execute("SELECT id FROM nodes").fetchall()
        return {row["id"] for row in rows}

    def edge_exists(self, source_id: str, target_id: str, edge_type: str) -> bool:
        """Return True if a directed edge (source→target, type) already exists."""
        row = self._conn.execute(
            "SELECT id FROM edges WHERE source_id=? AND target_id=? AND edge_type=?",
            (source_id, target_id, edge_type),
        ).fetchone()
        return row is not None

    def get_nodes_by_type(self, node_type: str) -> list[dict[str, Any]]:
        """Return all nodes with the given node_type as a list of dicts."""
        rows = self._conn.execute(
            "SELECT id, title, content FROM nodes WHERE node_type = ?",
            (node_type,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_node_type_batch(self, updates: list[tuple[str, str]]) -> None:
        """Bulk-update node types. *updates* is a list of (new_type, node_id) tuples."""
        if not updates:
            return
        self._conn.executemany(
            "UPDATE nodes SET node_type = ? WHERE id = ?",
            updates,
        )
        self._conn.commit()

    def get_type_distribution(self) -> dict[str, int]:
        """Return a mapping of node_type → count across all nodes."""
        rows = self._conn.execute(
            "SELECT node_type, COUNT(*) AS cnt FROM nodes GROUP BY node_type"
        ).fetchall()
        return {row["node_type"]: row["cnt"] for row in rows}

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_keywords(
        feature_spec: str | None,
        error_pattern: str | None,
        file_patterns: list[str] | None,
    ) -> list[str]:
        """Extract FTS-safe keywords from query context."""
        tokens: list[str] = []

        for text in [feature_spec, error_pattern]:
            if not text:
                continue
            # Split on whitespace and punctuation, keep 4+ char tokens
            words = re.findall(r"[a-zA-Z][a-zA-Z0-9_]{3,}", text)
            tokens.extend(words)

        if file_patterns:
            for pat in file_patterns:
                # Extract filename stem (e.g. "auth" from "src/auth.py")
                stem = re.sub(r"[^a-zA-Z0-9]", " ", pat)
                tokens.extend(w for w in stem.split() if len(w) >= 4)

        # Deduplicate while preserving order
        seen: set[str] = set()
        result: list[str] = []
        for t in tokens:
            if t.lower() not in seen:
                seen.add(t.lower())
                result.append(t)
        return result

    @staticmethod
    def _detect_stack(feature_spec: str | None) -> str | None:
        """Heuristic stack detection from feature spec text."""
        return _detect_stack_fn(feature_spec)
