"""
Migration: parse flat markdown learnings files → SQLite knowledge graph.

Supported formats
-----------------
1. Compressed core.md format (inline, one line per entry):
     **L-00001:** Learning text here.
     **M-00042:** Meta entry text.

2. Full graph-schema format (block entries with optional frontmatter fields):
     ## L-00001 — Optional title here
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
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from auto_sdd_v2.knowledge_system._utils import detect_stack
from auto_sdd_v2.knowledge_system.store import KnowledgeStore

logger = logging.getLogger(__name__)

# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class RawEntry:
    entry_id: str           # e.g. "L-00001"
    content: str            # full text body
    title: str | None = None            # captured from block header (S-1)
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

# ── Parser ────────────────────────────────────────────────────────────────────

# Matches: **L-00001:** or **M-00042:** (compressed inline format)
# Note: the colon is INSIDE the bold markers: **ID:**  not **ID**:
_INLINE_RE = re.compile(
    r"^\*\*([LMUK]-\d{5}):\*\*\s*(.+)$",
    re.MULTILINE,
)

# Matches: ## L-00001 or ## L-00001 — Optional title here (block format header)
# group(1) = ID, group(2) = optional title after em-dash/hyphen (S-1)
_BLOCK_HEADER_RE = re.compile(
    r"^#{1,3}\s+([LMUK]-\d{5})(?:\s+[—\-–]\s+(.+))?$",
    re.MULTILINE,
)

# Matches frontmatter-style lines inside a block entry
_FIELD_RE = re.compile(
    r"^(type|tags|confidence|status|date|related)\s*:\s*(.+)$",
    re.IGNORECASE,
)

# Matches leading separator lines (--- or ----) (N-1)
_SEPARATOR_RE = re.compile(r"^---+\s*\n?")


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

        # Capture optional title from header (S-1)
        raw_title = header_match.group(2)
        entry_title = raw_title.strip() if raw_title else None

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

        # Body = lines after frontmatter, stripped of leading separator lines (N-1)
        body_lines = lines[body_start:]
        body = _SEPARATOR_RE.sub("", "\n".join(body_lines).strip()).strip()

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
            title=entry_title,
            tags=tags,
            node_type_hint=type_hint,
            status_hint=status_hint,
            related=related,
            source_file=path,
        ))

    return entries


def _entry_richness(entry: RawEntry) -> int:
    """Score an entry's metadata richness for deduplication preference (B-1)."""
    score = 0
    if entry.status_hint and entry.status_hint != "active":
        score += 1
    if entry.tags:
        score += 1
    if entry.related:
        score += 1
    return score


def parse_files(paths: list[str]) -> list[RawEntry]:
    """
    Parse multiple markdown files and return all entries deduplicated by ID.

    When the same ID appears in multiple files, the entry with more metadata
    (non-default status, tags, related IDs) is kept over the stripped-down one.
    This ensures richer entries from type-specific files win over core.md summaries.
    """
    by_id: dict[str, RawEntry] = {}
    for path in paths:
        for entry in parse_file(path):
            existing = by_id.get(entry.entry_id)
            if existing is None or _entry_richness(entry) > _entry_richness(existing):
                by_id[entry.entry_id] = entry
    return list(by_id.values())


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
    existing = store.get_all_node_ids()

    for entry in entries:
        if entry.entry_id in existing:
            skipped += 1
            if verbose:
                logger.info("  SKIP  %s (already present)", entry.entry_id)
            continue

        node_type = entry.node_type_hint or "instance"
        status = entry.status_hint or "active"
        stack = detect_stack(entry.content)

        # Build title: prefer header title (S-1), fall back to first sentence
        if entry.title:
            title = entry.title[:80]
        else:
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
                logger.info("  INSERT %s: %s", entry.entry_id, title[:60])
        except Exception as exc:
            logger.error("  ERROR  %s: %s", entry.entry_id, exc)

    # Create edges for 'related' references (only if both nodes now exist)
    for entry in entries:
        if not entry.related:
            continue
        for related_id in entry.related:
            if entry.entry_id in existing and related_id in existing:
                # Avoid duplicate edges: check first
                if not store.edge_exists(entry.entry_id, related_id, "co_occurs"):
                    try:
                        store.add_edge(entry.entry_id, related_id, "co_occurs")
                        edges_added += 1
                    except Exception:
                        pass  # FK violation if target missing — skip

    return {"inserted": inserted, "skipped": skipped, "edges_added": edges_added}


# ── Node re-typing ────────────────────────────────────────────────────────────

# Keyword sets for deterministic type classification (no LLM judgment).
# Priority order: mistake > universal > framework > technology > instance (no change).

_RETYPE_MISTAKE: list[str] = [
    "failure", "error", "bug", "broke", "crash", "regression",
    "failed", "broken", "incorrect", "pitfall", "trap",
]

_RETYPE_UNIVERSAL: list[str] = [
    "always", "never", "every", "any project", "any feature",
    "constitutional", "all projects", "regardless",
    "any stack", "any codebase", "universal principle",
]

_RETYPE_FRAMEWORK: list[str] = [
    "next.js", "nextjs", "next/", "react", "prisma", "tailwind",
    "django", "fastapi", "remix", "nuxt", "sveltekit",
    "angular", "vue.js", "vuejs", "flask", "express.js",
    "expressjs", "gatsby", "astro",
]

_RETYPE_TECHNOLOGY: list[str] = [
    "sqlite", "postgres", "postgresql", "redis", "docker",
    "kubernetes", "webpack", "vite", "eslint", "typescript",
    "pytest", "jest", "mypy", "pip install", "npm install",
    "yarn", "github actions", "ci/cd", "fts5",
]


def _classify_node_type(title: str, content: str) -> str | None:
    """Return the reclassified type for a node, or None to leave as 'instance'.

    Priority: mistake > universal > framework > technology > None.
    Uses keyword matching on title (full) and first 500 chars of content only.
    Deterministic — no LLM judgment.
    """
    lower_title = title.lower()
    # Combine title + beginning of content for matching
    lower_combined = (title + " " + content[:500]).lower()

    # mistake: title must contain a keyword (primary-topic check)
    if any(kw in lower_title for kw in _RETYPE_MISTAKE):
        return "mistake"

    # universal: title or early content contains broad-applicability signals
    if any(kw in lower_combined for kw in _RETYPE_UNIVERSAL):
        return "universal"

    # framework: title or early content names a specific framework
    if any(kw in lower_combined for kw in _RETYPE_FRAMEWORK):
        return "framework"

    # technology: title or early content names a specific technology
    if any(kw in lower_combined for kw in _RETYPE_TECHNOLOGY):
        return "technology"

    return None


def retype_nodes(
    store: KnowledgeStore,
    *,
    verbose: bool = False,
) -> dict[str, int]:
    """Reclassify 'instance' nodes to more specific types using keyword analysis.

    Idempotent: only processes nodes currently typed 'instance'. Nodes already
    typed universal/framework/technology/mistake/meta are left unchanged.

    Returns the full type distribution after retyping.
    """
    rows = store.get_nodes_by_type("instance")

    updates: list[tuple[str, str]] = []  # (new_type, node_id)
    for row in rows:
        node_id = row["id"]
        title = row["title"] or ""
        content = row["content"] or ""
        new_type = _classify_node_type(title, content)
        if new_type is not None:
            updates.append((new_type, node_id))
            if verbose:
                logger.info("  RETYPE %s → %s", node_id, new_type)

    store.update_node_type_batch(updates)

    logger.info(
        "retype_nodes: %d/%d instance nodes retyped",
        len(updates), len(rows),
    )

    return store.get_type_distribution()


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
    parser.add_argument(
        "--retype",
        action="store_true",
        help=(
            "Reclassify 'instance' nodes to universal/framework/technology/mistake "
            "using keyword matching. Can be run standalone (skips migration) or "
            "combined with a migration run."
        ),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    store = KnowledgeStore(args.db)

    if not args.retype:
        # Normal migration path
        files: list[str] = args.files or find_learnings_files(args.base_dir)

        if not files:
            logger.warning("No learnings files found. Nothing to migrate.")
            store.close()
            return 0

        logger.info("Migrating %d file(s) into %s", len(files), args.db)

        entries = parse_files(files)
        logger.info("Parsed %d entries from %d file(s).", len(entries), len(files))

        stats = migrate(store, entries, verbose=args.verbose)

        logger.info(
            "Done. inserted=%d skipped=%d edges_added=%d",
            stats["inserted"], stats["skipped"], stats["edges_added"],
        )

    # Run retype if --retype flag set (can combine with migration above)
    if args.retype:
        logger.info("Running retype_nodes against %s", args.db)
        dist = retype_nodes(store, verbose=args.verbose)
        logger.info("Type distribution after retype:")
        for node_type, count in sorted(dist.items()):
            logger.info("  %-12s %d", node_type, count)

    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
