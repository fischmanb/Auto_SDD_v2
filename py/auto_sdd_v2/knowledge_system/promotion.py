"""Standalone promotion runner for the knowledge system.

Runs the full promotion lifecycle against a knowledge.db:
  active → promoted   (≥1 successful injection, scope well-defined)
  promoted → hardened (≥3 successful injections, lift > 0)
  hardened → promoted (demotion: ≥5 injections, lift ≤ 0)

Usage:
    python -m auto_sdd_v2.knowledge_system.promotion
    python -m auto_sdd_v2.knowledge_system.promotion --db-path .sdd-knowledge/knowledge.db
    python -m auto_sdd_v2.knowledge_system.promotion --verbose
"""
from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def run_promotion(db_path: str) -> dict[str, int]:
    """Run the promotion job against *db_path*.

    Returns a summary: {promoted: N, hardened: N, demoted: N, total: N}.
    Returns all-zero dict on any error so callers can continue safely.
    """
    try:
        from auto_sdd_v2.knowledge_system.store import KnowledgeStore

        store = KnowledgeStore(db_path)
        try:
            events = store.promote()
        finally:
            store.close()

        promoted = sum(
            1 for e in events if e.get("from") == "active" and e.get("to") == "promoted"
        )
        hardened = sum(1 for e in events if e.get("to") == "hardened")
        demoted = sum(
            1 for e in events if e.get("from") == "hardened" and e.get("to") == "promoted"
        )
        summary = {
            "promoted": promoted,
            "hardened": hardened,
            "demoted": demoted,
            "total": len(events),
        }
        logger.info(
            "Promotion run complete: %d promoted, %d hardened, %d demoted",
            promoted, hardened, demoted,
        )
        return summary

    except Exception as exc:
        logger.warning("Promotion run failed (non-fatal): %s", exc)
        return {"promoted": 0, "hardened": 0, "demoted": 0, "total": 0, "error": True}


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Knowledge system promotion runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--db-path",
        default=".sdd-knowledge/knowledge.db",
        help="Path to knowledge.db (default: .sdd-knowledge/knowledge.db)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    summary = run_promotion(args.db_path)
    if summary.get("error"):
        print("WARNING: promotion run failed — check logs for details", file=sys.stderr)
        sys.exit(1)
    if summary["total"] == 0:
        print("No promotions needed")
    else:
        print(
            f"Promotion complete: "
            f"{summary['promoted']} promoted, "
            f"{summary['hardened']} hardened, "
            f"{summary['demoted']} demoted "
            f"({summary['total']} total events)"
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
