"""Shared utilities for the knowledge system."""

_STACK_PATTERNS: list[tuple[str, list[str]]] = [
    ("nextjs",     ["next.js", "nextjs", "next/", "app router", "use client", "use server"]),
    ("react",      ["react", "jsx", "tsx", "usestate", "useffect", "component"]),
    ("prisma",     ["prisma", "prisma client", "prisma schema"]),
    ("tailwind",   ["tailwind", "tw-", "classname"]),
    ("typescript", ["typescript", "type error", ".ts", ".tsx"]),
    ("python",     ["python", ".py", "pytest", "mypy", "pydantic", "fastapi"]),
    ("sqlite",     ["sqlite", "sqlite3", "fts5", "pragma"]),
    ("git",        ["git ", "git commit", "git branch", "git merge", "rebase", "stash"]),
]


def detect_stack(text: str | None) -> str | None:
    """Detect the technology stack from text content. Returns None for empty input."""
    if not text:
        return None
    lower = text.lower()
    for stack_name, hints in _STACK_PATTERNS:
        if any(h in lower for h in hints):
            return stack_name
    return None
