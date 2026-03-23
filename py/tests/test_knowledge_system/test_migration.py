"""Tests for knowledge_system.migration: parser and migrate() function."""

import os
import textwrap
import pytest

from auto_sdd_v2.knowledge_system.migration import (
    parse_file,
    parse_files,
    migrate,
    find_learnings_files,
    RawEntry,
)
from auto_sdd_v2.knowledge_system.store import KnowledgeStore


@pytest.fixture
def store(tmp_path):
    s = KnowledgeStore(str(tmp_path / "test.db"))
    yield s
    s.close()


# ── Parser: inline format ─────────────────────────────────────────────────────

class TestParseInlineFormat:
    def test_parses_single_l_entry(self, tmp_path):
        md = tmp_path / "core.md"
        md.write_text("**L-00001:** Never trust agent self-assessments.\n")
        entries = parse_file(str(md))
        assert len(entries) == 1
        assert entries[0].entry_id == "L-00001"
        assert "Never trust" in entries[0].content

    def test_parses_multiple_entries(self, tmp_path):
        md = tmp_path / "core.md"
        md.write_text(
            "**L-00001:** First entry.\n"
            "**L-00002:** Second entry.\n"
            "**M-00001:** A meta entry.\n"
        )
        entries = parse_file(str(md))
        ids = {e.entry_id for e in entries}
        assert ids == {"L-00001", "L-00002", "M-00001"}

    def test_l_prefix_maps_to_instance(self, tmp_path):
        md = tmp_path / "core.md"
        md.write_text("**L-00001:** Content here.\n")
        entries = parse_file(str(md))
        assert entries[0].node_type_hint == "instance"

    def test_m_prefix_maps_to_meta(self, tmp_path):
        md = tmp_path / "core.md"
        md.write_text("**M-00001:** Content here.\n")
        entries = parse_file(str(md))
        assert entries[0].node_type_hint == "meta"

    def test_k_prefix_maps_to_mistake(self, tmp_path):
        md = tmp_path / "core.md"
        md.write_text("**K-00001:** Content here.\n")
        entries = parse_file(str(md))
        assert entries[0].node_type_hint == "mistake"

    def test_u_prefix_maps_to_universal(self, tmp_path):
        md = tmp_path / "core.md"
        md.write_text("**U-00001:** Content here.\n")
        entries = parse_file(str(md))
        assert entries[0].node_type_hint == "universal"

    def test_source_file_recorded(self, tmp_path):
        md = tmp_path / "core.md"
        md.write_text("**L-00001:** Content.\n")
        entries = parse_file(str(md))
        assert entries[0].source_file == str(md)

    def test_ignores_non_entry_lines(self, tmp_path):
        md = tmp_path / "core.md"
        md.write_text(
            "# Header\n\nSome intro text.\n\n"
            "**L-00001:** The real entry.\n\n"
            "Some footer.\n"
        )
        entries = parse_file(str(md))
        assert len(entries) == 1
        assert entries[0].entry_id == "L-00001"


# ── Parser: block format ──────────────────────────────────────────────────────

class TestParseBlockFormat:
    def test_parses_basic_block(self, tmp_path):
        md = tmp_path / "learnings.md"
        md.write_text(textwrap.dedent("""\
            ## L-00001

            Full learning body text here.
            Can span multiple lines.
        """))
        entries = parse_file(str(md))
        assert len(entries) == 1
        assert entries[0].entry_id == "L-00001"
        assert "Full learning body text" in entries[0].content

    def test_parses_frontmatter_fields(self, tmp_path):
        md = tmp_path / "learnings.md"
        md.write_text(textwrap.dedent("""\
            ## L-00001
            type: universal
            tags: reliability, verification
            status: hardened
            related: L-00002, L-00003

            Body of the learning.
        """))
        entries = parse_file(str(md))
        assert len(entries) == 1
        e = entries[0]
        assert e.node_type_hint == "universal"
        assert "reliability" in e.tags
        assert "verification" in e.tags
        assert e.status_hint == "hardened"
        assert "L-00002" in e.related
        assert "L-00003" in e.related

    def test_parses_multiple_blocks(self, tmp_path):
        md = tmp_path / "learnings.md"
        md.write_text(textwrap.dedent("""\
            ## L-00001
            type: instance

            First entry body.

            ## L-00002
            type: mistake

            Second entry body.
        """))
        entries = parse_file(str(md))
        ids = {e.entry_id for e in entries}
        assert ids == {"L-00001", "L-00002"}

    def test_h1_and_h3_headers_work(self, tmp_path):
        md = tmp_path / "learnings.md"
        md.write_text(
            "# L-00001\nBody A.\n\n### L-00002\nBody B.\n"
        )
        entries = parse_file(str(md))
        ids = {e.entry_id for e in entries}
        assert "L-00001" in ids
        assert "L-00002" in ids

    def test_status_alias_validated_maps_to_promoted(self, tmp_path):
        md = tmp_path / "learnings.md"
        md.write_text("## L-00001\nstatus: validated\n\nBody.\n")
        entries = parse_file(str(md))
        assert entries[0].status_hint == "promoted"


# ── Parser: edge cases ────────────────────────────────────────────────────────

class TestParseEdgeCases:
    def test_nonexistent_file_returns_empty(self):
        entries = parse_file("/nonexistent/path/learnings.md")
        assert entries == []

    def test_empty_file_returns_empty(self, tmp_path):
        md = tmp_path / "empty.md"
        md.write_text("")
        entries = parse_file(str(md))
        assert entries == []

    def test_file_with_no_entries_returns_empty(self, tmp_path):
        md = tmp_path / "no_entries.md"
        md.write_text("# Some random document\n\nWith no learnings entries.\n")
        entries = parse_file(str(md))
        assert entries == []

    def test_deduplicates_same_id_in_both_formats(self, tmp_path):
        """If inline and block both have L-00001, only one entry should be returned."""
        md = tmp_path / "mixed.md"
        md.write_text(
            "**L-00001:** Inline version.\n\n"
            "## L-00001\ntype: instance\n\nBlock version.\n"
        )
        entries = parse_file(str(md))
        l_entries = [e for e in entries if e.entry_id == "L-00001"]
        assert len(l_entries) == 1

    def test_mixed_formats_in_same_file(self, tmp_path):
        md = tmp_path / "mixed.md"
        md.write_text(
            "**L-00001:** Inline entry.\n"
            "**L-00002:** Another inline.\n\n"
            "## L-00003\n\nBlock entry.\n"
        )
        entries = parse_file(str(md))
        ids = {e.entry_id for e in entries}
        assert ids == {"L-00001", "L-00002", "L-00003"}


class TestParseFiles:
    def test_multiple_files_merged(self, tmp_path):
        f1 = tmp_path / "a.md"
        f2 = tmp_path / "b.md"
        f1.write_text("**L-00001:** Entry from file 1.\n")
        f2.write_text("**L-00002:** Entry from file 2.\n")
        entries = parse_files([str(f1), str(f2)])
        ids = {e.entry_id for e in entries}
        assert ids == {"L-00001", "L-00002"}

    def test_duplicate_ids_across_files_deduplicated(self, tmp_path):
        f1 = tmp_path / "a.md"
        f2 = tmp_path / "b.md"
        f1.write_text("**L-00001:** From file 1.\n")
        f2.write_text("**L-00001:** From file 2.\n")
        entries = parse_files([str(f1), str(f2)])
        assert len([e for e in entries if e.entry_id == "L-00001"]) == 1

    def test_missing_files_ignored(self, tmp_path):
        f1 = tmp_path / "real.md"
        f1.write_text("**L-00001:** Real entry.\n")
        entries = parse_files([str(f1), "/nonexistent/file.md"])
        assert len(entries) == 1


# ── Migration: migrate() ──────────────────────────────────────────────────────

class TestMigrateFunction:
    def test_inserts_entries(self, store, tmp_path):
        md = tmp_path / "core.md"
        md.write_text("**L-00001:** First.\n**L-00002:** Second.\n")
        entries = parse_file(str(md))
        stats = migrate(store, entries)
        assert stats["inserted"] == 2
        assert stats["skipped"] == 0

    def test_idempotent_skips_existing(self, store, tmp_path):
        md = tmp_path / "core.md"
        md.write_text("**L-00001:** Entry.\n")
        entries = parse_file(str(md))

        migrate(store, entries)  # first run
        stats = migrate(store, entries)  # second run

        assert stats["inserted"] == 0
        assert stats["skipped"] == 1

    def test_nodes_queryable_after_migration(self, store, tmp_path):
        md = tmp_path / "core.md"
        md.write_text("**L-00001:** Some content about nextjs env vars.\n")
        entries = parse_file(str(md))
        migrate(store, entries)

        node = store.get_node("L-00001")
        assert node is not None
        assert node["id"] == "L-00001"

    def test_edges_created_for_related(self, store, tmp_path):
        md = tmp_path / "learnings.md"
        md.write_text(textwrap.dedent("""\
            ## L-00001
            related: L-00002

            First entry.

            ## L-00002

            Second entry.
        """))
        entries = parse_file(str(md))
        stats = migrate(store, entries)
        assert stats["edges_added"] == 1

        edges = store.get_edges("L-00001")
        assert len(edges) == 1
        edge_ids = {(e["source_id"], e["target_id"]) for e in edges}
        assert ("L-00001", "L-00002") in edge_ids

    def test_edges_idempotent(self, store, tmp_path):
        md = tmp_path / "learnings.md"
        md.write_text(textwrap.dedent("""\
            ## L-00001
            related: L-00002

            First.

            ## L-00002

            Second.
        """))
        entries = parse_file(str(md))
        migrate(store, entries)
        stats2 = migrate(store, entries)  # second run
        assert stats2["edges_added"] == 0  # no duplicate edges

    def test_status_preserved_from_frontmatter(self, store, tmp_path):
        md = tmp_path / "learnings.md"
        md.write_text("## L-00001\nstatus: hardened\n\nBody.\n")
        entries = parse_file(str(md))
        migrate(store, entries)
        node = store.get_node("L-00001")
        assert node is not None
        assert node["status"] == "hardened"

    def test_stack_detected_from_content(self, store, tmp_path):
        md = tmp_path / "core.md"
        md.write_text(
            "**L-00001:** NEXT_PUBLIC_ prefix required for client components in Next.js.\n"
        )
        entries = parse_file(str(md))
        migrate(store, entries)
        node = store.get_node("L-00001")
        assert node is not None
        assert node["stack"] == "nextjs"

    def test_fts_searchable_after_migration(self, store, tmp_path):
        md = tmp_path / "core.md"
        md.write_text("**L-00001:** unique_fts_test_token_xyzzy content.\n")
        entries = parse_file(str(md))
        migrate(store, entries)

        rows = store._conn.execute(
            "SELECT id FROM nodes_fts WHERE nodes_fts MATCH 'unique_fts_test_token_xyzzy'"
        ).fetchall()
        ids = [r[0] for r in rows]
        assert "L-00001" in ids


# ── S-6: Integration test against real core.md / type-specific file format ───

class TestRealFormatIntegration:
    """S-6: Verify parser behaviour against the actual learnings file format."""

    _CORE_MD_SNIPPET = textwrap.dedent("""\
        ## L-00001 — Agent self-assessments are unreliable
        **Source:** `failure-patterns.md`
        **Why core:** Foundation learning.

        Agent self-assessments have proven unreliable in practice.
        Always use machine-checkable gates.
    """)

    _RICH_SNIPPET = textwrap.dedent("""\
        ## L-00001 — Agent self-assessments are unreliable
        type: instance
        tags: reliability, agent-behavior
        status: hardened
        related: L-00016

        Agent self-assessments have proven unreliable in practice.
        Always use machine-checkable gates.
    """)

    def test_title_extracted_from_header(self, tmp_path):
        """S-1: title after em-dash in header must be captured, not discarded."""
        md = tmp_path / "core.md"
        md.write_text(self._CORE_MD_SNIPPET)
        entries = parse_file(str(md))
        assert len(entries) == 1
        e = entries[0]
        assert e.entry_id == "L-00001"
        assert e.title == "Agent self-assessments are unreliable"

    def test_title_used_in_migration_not_source_line(self, store, tmp_path):
        """S-1: migrate() must use header title, not '**Source:** failure-patterns'."""
        md = tmp_path / "core.md"
        md.write_text(self._CORE_MD_SNIPPET)
        entries = parse_file(str(md))
        migrate(store, entries)
        node = store.get_node("L-00001")
        assert node is not None
        assert node["title"] == "Agent self-assessments are unreliable"
        assert "Source" not in node["title"]

    def test_rich_entry_wins_over_core_md_inline(self, tmp_path):
        """B-1: type-specific file with tags/status/related must win over core.md inline."""
        core = tmp_path / "core.md"
        rich = tmp_path / "failure-patterns.md"
        # core.md has the stripped inline format (no tags/status/related)
        core.write_text("**L-00001:** Agent self-assessments are unreliable.\n")
        # failure-patterns.md has the full graph-schema format
        rich.write_text(self._RICH_SNIPPET)

        # Parse core.md first (as _DEFAULT_PATHS orders it), then rich file
        entries = parse_files([str(core), str(rich)])
        l_entries = [e for e in entries if e.entry_id == "L-00001"]
        assert len(l_entries) == 1
        winner = l_entries[0]
        # The richer entry must win
        assert winner.status_hint == "hardened"
        assert "reliability" in winner.tags
        assert "L-00016" in winner.related

    def test_content_parsed_correctly_from_real_format(self, tmp_path):
        """Block body must not start with the **Source:** frontmatter line."""
        md = tmp_path / "core.md"
        md.write_text(self._CORE_MD_SNIPPET)
        entries = parse_file(str(md))
        assert len(entries) == 1
        # Content should contain the actual learning text
        assert "Agent self-assessments have proven unreliable" in entries[0].content


# ── find_learnings_files ──────────────────────────────────────────────────────

class TestFindLearningsFiles:
    def test_returns_empty_for_empty_dir(self, tmp_path):
        result = find_learnings_files(str(tmp_path))
        assert result == []

    def test_finds_existing_learnings_files(self, tmp_path):
        learn_dir = tmp_path / "learnings"
        learn_dir.mkdir()
        (learn_dir / "core.md").write_text("**L-00001:** entry.\n")

        result = find_learnings_files(str(tmp_path))
        assert any("core.md" in p for p in result)

    def test_only_returns_existing_files(self, tmp_path):
        learn_dir = tmp_path / "learnings"
        learn_dir.mkdir()
        (learn_dir / "core.md").write_text("content")
        # pending.md does NOT exist

        result = find_learnings_files(str(tmp_path))
        for path in result:
            assert os.path.isfile(path)
