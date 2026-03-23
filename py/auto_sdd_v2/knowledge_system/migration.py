"""
Migration: parse flat markdown learnings files → SQLite knowledge graph.

Supported formats
-----------------
1. Compressed core.md format (inline, one line per entry):
     **L-00001:** Learning text here.
     **M-00042:** Meta entry text.

2. Full graph-schema format (block entries with optional frontmatter fields):
     ## L-00001
     type: instance
     tags: reliability, agent-behavior
     confidence: 0.95
     status: hardened
     date: 2024-01-15
     related: L-00016, L-00162

     Learning body text.
     Can span multiple paragraphs.

     ---  (separator between entries, optional)

Both formats may appear in the same file. The parser handles them both.

Usage
-----
    python -m auto_sdd_v2.knowledge_system.migration \
        --db /path/to/knowledge.db \
        --files learnings/core.md learnings/failure-patterns.md

Idempotent: nodes already present (matched by ID) are silently skipped.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from auto_sdd_v2.knowledge_system.store import KnowledgeStore

# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class RawEntry:
    entry_id: str           # e.g. "L-00001"
    content: str            # full text body
    tags: list[str] = field(default_factory=list)
    node_type_hint: str | None = None   # from 'type:' field if present
    status_hint: str | None = None      # from 'status:' field
    related: list[str] = field(default_factory=list)   # referenced IDs
    source_file: str | None = None

# ── ID prefix → node_type mapping ─────────────────────────────────────────────

_PREFIX_TO_TYPE: dict[str, str] = {
    "L": "instance",
    "M": "meta",
    "U": "universal",
    "K": "mistake",
}

_VALID_NODE_TYPES = frozenset({"universal", "framework", "technology", "instance", "mistake", "meta"})

_STATUS_MAP: dict[str, str] = {
    "hardened":   "hardened",
    "promoted":   "promoted",
    "validated":  "promoted",   # legacy alias
    "active":     "active",
    "deprecated": "deprecated",
    "instance":   "active",     # old type-as-status labels
}

# ── Stack detection keywords ──────────────────────────────────────────────────

_STACK_PATTERNS: list[tuple[str, list[str]]] = [
    ("nextjs",     ["next.js", "nextjs", "next/", "app router", "use client", "use server"]),
    ("react",      ["react", "jsx", "tsx", "usestate", "useffect", "component"]),
    ("prisma",     ["prisma", "prisma client", "prisma schema"]),
    ("tailwind",   ["tailwind", "tw-", "classname", "className"]),
    ("typescript", ["typescript", "type error", ".ts", ".tsx", "mypy"]),
    ("python",     ["python", ".py", "pytest", "mypy", "pydantic", "fastapi"]),
    ("sqlite",     ["sqlite", "sqlite3", "fts5", "pragma"]),
    ("git",        ["git ", "commit", "branch", "merge", "rebase", "stash"]),
]


def _detect_stack(text: str) -> str | None:
    lower = text.lower()
    for stack_name, hints in _STACK_PATTERNS:
        if any(h in lower for h in hints):
            return stack_name
    return None


# ── Parser ────────────────────────────────────────────────────────────────────

# Matches: **L-00001:** or **M-00042:** (compressed inline format)
# Note: the colon is INSIDE the bold markers: **ID:**  not **ID**:
_INLINE_RE = re.compile(
    r"^\*\*([LMUK]-\d{5}):\*\*\s*(.+)$",
    re.MULTILINE,
)

# Matches: ## L-00001 or # L-00001 (block format header)
_BLOCK_HEADER_RE = re.compile(
    r"^#{1,3}\s+([LMUK]-\d{5})\b",
    re.MULTILINE,
)

# Matches frontmatter-style lines inside a block entry
_FIELD_RE = re.compile(
    r"^(type|tags|confidence|status|date|related)\s*:\s*(.+)$",
    re.IGNORECASE,
)


def parse_file(path: str) -> list[RawEntry]:
    """
    Parse a single markdown file and return all learnings entries found.
    Returns an empty list if the file does not exist or is empty.
    """
    p = Path(path)
    if not p.exists():
        return []

    text = p.read_text(encoding="utf-8")
    if not text.strip():
        return []

    entries: list[RawEntry] = []
    seen_ids: set[str] = set()

    # ── Pass 1: inline format ─────────────────────────────────────────────
    for match in _INLINE_RE.finditer(text):
        entry_id = match.group(1)
        content = match.group(2).strip()
        if entry_id in seen_ids:
            continue
        seen_ids.add(entry_id)
        prefix = entry_id[0]
        entries.append(RawEntry(
            entry_id=entry_id,
            content=content,
            node_type_hint=_PREFIX_TO_TYPE.get(prefix, "instance"),
            source_file=path,
        ))

    # ── Pass 2: block format ──────────────────────────────────────────────
    # Split on block headers; each segment is one entry
    headers = list(_BLOCK_HEADER_RE.finditer(text))
    for i, header_match in enumerate(headers):
        entry_id = header_match.group(1)
        if entry_id in seen_ids:
            continue  # already captured inline

        # Segment: from end of header line to start of next header (or EOF)
        start = header_match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        segment = text[start:end].strip()

        # Parse frontmatter fields from top of segment
        field_values: dict[str, str] = {}
        lines = segment.splitlines()
        body_start = 0
        for j, line in enumerate(lines):
            fm = _FIELD_RE.match(line.strip())
            if fm:
                field_values[fm.group(1).lower()] = fm.group(2).strip()
                body_start = j + 1
            elif line.strip() and not line.strip().startswith("#"):
                break

        # Body = lines after frontmatter, stripped of leading separators
        body_lines = lines[body_start:]
        body = "\n".join(body_lines).strip().lstrip("-").strip()

        if not body:
            body = segment  # fallback: use full segment

        # Parse tags
        tags: list[str] = []
        if "tags" in field_values:
            tags = [t.strip() for t in field_values["tags"].split(",") if t.strip()]

        # Parse related IDs
        related: list[str] = []
        if "related" in field_values:
            related = [
                r.strip()
                for r in re.split(r"[,\s]+", field_values["related"])
                if re.match(r"^[LMUK]-\d{5}$", r.strip())
            ]

        # Parse type hint
        type_hint_raw = field_values.get("type", "").lower()
        type_hint = type_hint_raw if type_hint_raw in _VALID_NODE_TYPES else _PREFIX_TO_TYPE.get(entry_id[0], "instance")

        # Parse status hint
        status_raw = field_values.get("status", "").lower()
        status_hint = _STATUS_MAP.get(status_raw, "active")

        seen_ids.add(entry_id)
        entries.append(RawEntry(
            entry_id=entry_id,
            content=body,
            tags=tags,
            node_type_hint=type_hint,
            status_hint=status_hint,
            related=related,
            source_file=path,
        ))

    return entries


def parse_files(paths: list[str]) -> list[RawEntry]:
    """Parse multiple markdown files and return all entries (deduplicated by ID)."""
    all_entries: list[RawEntry] = []
    seen: set[str] = set()
    for path in paths:
        for entry in parse_file(path):
            if entry.entry_id not in seen:
                seen.add(entry.entry_id)
                all_entries.append(entry)
    return all_entries


# ── Migration runner ──────────────────────────────────────────────────────────

def migrate(
    store: KnowledgeStore,
    entries: list[RawEntry],
    *,
    verbose: bool = False,
) -> dict[str, int]:
    """
    Migrate parsed entries into the KnowledgeStore.

    Idempotent: entries whose IDs already exist in the store are skipped.

    Returns a stats dict: {'inserted': N, 'skipped': N, 'edges_added': N}
    """
    inserted = 0
    skipped = 0
    edges_added = 0

    # Build ID set of nodes already in the store
    existing = {
        row["id"]
        for row in store._conn.execute("SELECT id FROM nodes").fetchall()
    }

    for entry in entries:
        if entry.entry_id in existing:
            skipped += 1
            if verbose:
                print(f"  SKIP  {entry.entry_id} (already present)")
            continue

        node_type = entry.node_type_hint or "instance"
        status = entry.status_hint or "active"
        stack = _detect_stack(entry.content)

        # Build title from first sentence (≤80 chars)
        first_sentence = re.split(r"[.!?\n]", entry.content)[0].strip()
        title = first_sentence[:80] if first_sentence else entry.entry_id

        metadata: dict[str, Any] = {}
        if entry.tags:
            metadata["tags"] = entry.tags
        if entry.related:
            metadata["related"] = entry.related

        try:
            store.add_node(
                node_type=node_type,
                title=title,
                content=entry.content,
                node_id=entry.entry_id,
                stack=stack,
                source_file=entry.source_file,
                status=status,
                metadata=metadata if metadata else None,
            )
            existing.add(entry.entry_id)
            inserted += 1
            if verbose:
                print(f"  INSERT {entry.entry_id}: {title[:60]}")
        except Exception as exc:
            if verbose:
                print(f"  ERROR  {entry.entry_id}: {exc}", file=sys.stderr)

    # Create edges for 'related' references (only if both nodes now exist)
    for entry in entries:
        if not entry.related:
            continue
        for related_id in entry.related:
            if entry.entry_id in existing and related_id in existing:
                # Avoid duplicate edges: check first
                dup = store._conn.execute(
                    "SELECT id FROM edges WHERE source_id=? AND target_id=? AND edge_type='co_occurs'",
                    (entry.entry_id, related_id),
                ).fetchone()
                if dup is None:
                    try:
                        store.add_edge(entry.entry_id, related_id, "co_occurs")
                        edges_added += 1
                    except Exception:
                        pass  # FK violation if target missing — skip

    return {"inserted": inserted, "skipped": skipped, "edges_added": edges_added}


# ── Default search paths ──────────────────────────────────────────────────────

_DEFAULT_PATHS = [
    "learnings/core.md",
    "learnings/pending.md",
    "learnings/failure-patterns.md",
    "learnings/process-rules.md",
    "learnings/empirical-findings.md",
    "learnings/architectural-rationale.md",
    "learnings/domain-knowledge.md",
    ".specs/learnings/general.md",
    ".specs/learnings/testing.md",
    ".specs/learnings/performance.md",
    ".specs/learnings/security.md",
    ".specs/learnings/api.md",
]


def find_learnings_files(base_dir: str = ".") -> list[str]:
    """Return existing learnings files from known paths relative to *base_dir*."""
    found = []
    for rel in _DEFAULT_PATHS:
        abs_path = os.path.join(base_dir, rel)
        if os.path.isfile(abs_path):
            found.append(abs_path)
    return found


# ── CLI entry point ───────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate flat markdown learnings files into the knowledge graph SQLite DB."
    )
    parser.add_argument(
        "--db",
        required=True,
        help="Path to the SQLite database file (will be created if absent).",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        help=(
            "Markdown files to import. "
            "If omitted, auto-discovers from known default paths in CWD."
        ),
    )
    parser.add_argument(
        "--base-dir",
        default=".",
        help="Base directory for auto-discovery (default: CWD).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print per-entry progress.",
    )
    args = parser.parse_args(argv)

    files: list[str] = args.files or find_learnings_files(args.base_dir)

    if not files:
        print("No learnings files found. Nothing to migrate.", file=sys.stderr)
        return 0

    print(f"Migrating {len(files)} file(s) into {args.db}")

    store = KnowledgeStore(args.db)
    entries = parse_files(files)
    print(f"Parsed {len(entries)} entries from {len(files)} file(s).")

    stats = migrate(store, entries, verbose=args.verbose)
    store.close()

    print(
        f"Done. inserted={stats['inserted']} skipped={stats['skipped']} "
        f"edges_added={stats['edges_added']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
