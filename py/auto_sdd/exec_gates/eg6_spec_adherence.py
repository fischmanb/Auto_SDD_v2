"""EG6: Spec Adherence ExecGate — deterministic post-build static analysis.

After EG2-EG5 pass (signals valid, builds, tests pass, commit authorized),
this gate checks that the agent's committed code structurally adheres to
the feature spec and systems-design metadata.

All checks are deterministic Python — no LLM involvement.

Checks:
    1. SOURCE_MATCH: agent's SOURCE_FILES signal matches git diff
    2. FILE_PLACEMENT: new files are in directories matching systems-design.md
    3. TOKEN_EXISTENCE: design tokens referenced in code exist in tokens.md
    4. NAMING_CONVENTION: file names follow conventions from systems-design.md
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from auto_sdd.lib.types import GateError

logger = logging.getLogger(__name__)


# ── Result type ──────────────────────────────────────────────────────────────


@dataclass
class SpecAdherenceResult:
    """Result of the spec adherence gate."""

    passed: bool = False
    checks_passed: list[GateError] = field(default_factory=list)
    checks_failed: list[GateError] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.passed:
            return f"Spec adherence OK ({len(self.checks_passed)} checks passed)"
        failed_codes = ", ".join(e.code for e in self.checks_failed)
        return (
            f"Spec adherence failed ({len(self.checks_failed)} issues: "
            f"{failed_codes})"
        )

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks_passed": [{"code": e.code, "detail": e.detail} for e in self.checks_passed],
            "checks_failed": [{"code": e.code, "detail": e.detail} for e in self.checks_failed],
            "summary": self.summary,
        }


# ── Individual checks ────────────────────────────────────────────────────────


def _get_diff_files(project_dir: Path, base_commit: str) -> set[str]:
    """Get set of files changed between base_commit and HEAD."""
    if not base_commit:
        return set()
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_commit, "HEAD"],
            capture_output=True, text=True,
            cwd=str(project_dir), timeout=15,
        )
        if result.returncode != 0:
            return set()
        return {
            line.strip() for line in result.stdout.splitlines()
            if line.strip()
        }
    except (subprocess.TimeoutExpired, OSError):
        return set()


def _check_source_match(
    source_files: list[str],
    diff_files: set[str],
    project_dir: Path,
) -> tuple[bool, GateError]:
    """Check 1: SOURCE_FILES signal matches files actually changed in the diff.

    Checks that every file in SOURCE_FILES was actually modified.
    Allows the diff to contain additional files (build artifacts, configs).
    """
    if not source_files:
        return True, GateError("SOURCE_MATCH", "no source files declared")

    # Normalize to relative paths
    normalized: list[str] = []
    for sf in source_files:
        p = Path(sf)
        try:
            rel = str(p.relative_to(project_dir)) if p.is_absolute() else sf
        except ValueError:
            rel = sf
        normalized.append(rel)

    missing = [f for f in normalized if f not in diff_files]
    if missing:
        return False, GateError(
            "SOURCE_NOT_IN_DIFF",
            f"{len(missing)} declared source file(s) not in diff: "
            f"{', '.join(missing[:5])}",
        )
    return True, GateError("SOURCE_MATCH", "all source files found in diff")


def _check_file_placement(
    source_files: list[str],
    project_dir: Path,
) -> tuple[bool, GateError]:
    """Check 2: New files are placed in expected directories.

    Reads systems-design.md to find "Directory Structure" section and
    extracts expected directory patterns. Checks source files are in
    recognized directories.
    """
    systems_path = project_dir / ".specs" / "systems-design.md"
    if not systems_path.is_file():
        return True, GateError("FILE_PLACEMENT", "no systems-design.md — skipped")

    try:
        content = systems_path.read_text()
    except OSError:
        return True, GateError("FILE_PLACEMENT", "systems-design.md unreadable — skipped")

    # Extract directory patterns from "Directory Structure" section
    allowed_dirs = _extract_directory_patterns(content)
    if not allowed_dirs:
        return True, GateError("FILE_PLACEMENT", "no directory patterns found — skipped")

    misplaced: list[str] = []
    for sf in source_files:
        parts = Path(sf).parts
        if not parts:
            continue
        top_dir = parts[0]
        # Allow .specs/ (spec files), and any directory mentioned in systems-design
        if top_dir.startswith("."):
            continue  # Hidden dirs (.specs, .github, etc.) are fine
        if top_dir not in allowed_dirs:
            misplaced.append(sf)

    if misplaced:
        return False, GateError(
            "FILE_MISPLACED",
            f"{len(misplaced)} file(s) in unexpected directories: "
            f"{', '.join(misplaced[:5])} "
            f"(expected: {', '.join(sorted(allowed_dirs)[:5])})",
        )
    return True, GateError("FILE_PLACEMENT", "all files in expected directories")


def _extract_directory_patterns(systems_design_content: str) -> set[str]:
    """Extract top-level directory names from systems-design.md."""
    dirs: set[str] = set()

    # Look for "Directory Structure" section
    in_section = False
    for line in systems_design_content.splitlines():
        lower = line.lower().strip()
        if "directory structure" in lower and lower.startswith("#"):
            in_section = True
            continue
        if in_section and lower.startswith("#"):
            break  # Next section
        if in_section:
            # Match directory references like "src/", "tests/", "lib/"
            for match in re.findall(r"\b([a-zA-Z][a-zA-Z0-9_-]*)/", line):
                dirs.add(match)

    # Always allow common top-level dirs even if not explicitly listed
    dirs.update({"src", "lib", "tests", "test", "docs", "scripts", "config"})
    return dirs


def _check_token_existence(
    source_files: list[str],
    project_dir: Path,
) -> tuple[bool, GateError]:
    """Check 3: Design tokens referenced in code exist in tokens.md.

    Scans source files for Tailwind-style classes and backtick-wrapped
    token references, then verifies they appear in tokens.md.
    """
    tokens_path = project_dir / ".specs" / "design-system" / "tokens.md"
    if not tokens_path.is_file():
        return True, GateError("TOKEN_EXISTENCE", "no tokens.md — skipped")

    try:
        tokens_content = tokens_path.read_text().lower()
    except OSError:
        return True, GateError("TOKEN_EXISTENCE", "tokens.md unreadable — skipped")

    # Extract all defined tokens from tokens.md (anything matching token pattern)
    defined_tokens: set[str] = set()
    for match in re.findall(r"`([a-z]+-[a-z0-9]+(?:-[a-z0-9]+)*)`", tokens_content):
        defined_tokens.add(match)
    # Also extract raw token-like values (color names, spacing values)
    for match in re.findall(r"([a-z]+-\d+(?:\.\d+)?)", tokens_content):
        defined_tokens.add(match)

    if not defined_tokens:
        return True, GateError("TOKEN_EXISTENCE", "no tokens defined — skipped")

    # Scan source files for token references
    # Pattern: backtick-wrapped tokens in comments/strings, or Tailwind class names
    token_pattern = re.compile(r"[a-z]+-[a-z0-9]+(?:-[a-z0-9]+)*")
    # Common Tailwind prefixes that reference design tokens
    tailwind_prefixes = {
        "bg-", "text-", "border-", "ring-", "shadow-", "rounded-",
        "p-", "px-", "py-", "pt-", "pb-", "pl-", "pr-",
        "m-", "mx-", "my-", "mt-", "mb-", "ml-", "mr-",
        "gap-", "space-", "w-", "h-", "min-w-", "min-h-",
        "max-w-", "max-h-", "font-", "tracking-", "leading-",
    }

    unknown_tokens: set[str] = set()
    for sf in source_files:
        full = project_dir / sf
        if not full.is_file():
            continue
        # Only check files that likely contain style references
        if not any(full.suffix == ext for ext in (".tsx", ".jsx", ".ts", ".js", ".css", ".html")):
            continue
        try:
            code = full.read_text()
        except OSError:
            continue

        # Find potential token references in class strings
        for match in re.findall(r'["\']([^"\']*)["\']', code):
            for cls in match.split():
                # Check if this is a Tailwind class with a token reference
                for prefix in tailwind_prefixes:
                    if cls.startswith(prefix):
                        token_part = cls[len(prefix):]
                        # Only flag specific color/spacing tokens, not arbitrary values
                        if re.match(r"[a-z]+-\d+$", token_part) or token_part in (
                            "xs", "sm", "md", "lg", "xl", "2xl", "3xl", "full",
                        ):
                            # These are standard Tailwind values, not custom tokens
                            continue
                        if token_part and not token_part[0].isdigit():
                            # Custom token reference — check if it exists
                            full_token = f"{prefix.rstrip('-')}-{token_part}"
                            if full_token not in defined_tokens and token_part not in defined_tokens:
                                unknown_tokens.add(cls)

    if unknown_tokens:
        return False, GateError(
            "TOKEN_UNKNOWN",
            f"{len(unknown_tokens)} class(es) reference unknown tokens: "
            f"{', '.join(sorted(unknown_tokens)[:10])}",
        )
    return True, GateError("TOKEN_EXISTENCE", "all token references valid")


def _check_naming_convention(
    source_files: list[str],
    project_dir: Path,
) -> tuple[bool, GateError]:
    """Check 4: File names follow naming conventions from systems-design.md.

    Common conventions:
    - React components: PascalCase (.tsx)
    - Utilities/hooks: camelCase (.ts)
    - Python modules: snake_case (.py)
    - Test files: test_*.py or *.test.ts
    """
    violations: list[str] = []

    for sf in source_files:
        p = Path(sf)
        stem = p.stem
        suffix = p.suffix

        # Skip hidden/config files
        if stem.startswith(".") or stem.startswith("_"):
            continue

        if suffix in (".tsx", ".jsx"):
            # React components should be PascalCase
            if not stem[0].isupper() and not stem.startswith("use"):
                violations.append(f"{sf} (expected PascalCase for component)")
        elif suffix == ".py":
            # Python modules should be snake_case
            if not re.match(r"^[a-z][a-z0-9_]*$", stem) and stem != "__init__":
                violations.append(f"{sf} (expected snake_case for Python module)")

    if violations:
        return False, GateError(
            "NAMING_VIOLATION",
            f"{len(violations)} naming issue(s): {'; '.join(violations[:5])}",
        )
    return True, GateError("NAMING_CONVENTION", "all file names follow conventions")


# ── Main gate ────────────────────────────────────────────────────────────────


def check_spec_adherence(
    project_dir: Path,
    source_files: list[str],
    base_commit: str = "",
) -> SpecAdherenceResult:
    """Run all spec adherence checks.

    This is the EG6 gate — structural validation of agent output against
    the spec and systems-design metadata. Runs after EG2-EG5 pass.

    All checks are deterministic. No LLM involvement.

    Args:
        project_dir: Project root directory.
        source_files: Files the agent declared via SOURCE_FILES signal.
        base_commit: HEAD before the agent ran (for diff computation).
    """
    result = SpecAdherenceResult()

    diff_files = _get_diff_files(project_dir, base_commit)

    checks = [
        _check_source_match(source_files, diff_files, project_dir),
        _check_file_placement(source_files, project_dir),
        _check_token_existence(source_files, project_dir),
        _check_naming_convention(source_files, project_dir),
    ]

    for passed, gate_error in checks:
        if passed:
            result.checks_passed.append(gate_error)
        else:
            result.checks_failed.append(gate_error)

    result.passed = len(result.checks_failed) == 0

    if result.passed:
        logger.info("EG6 spec adherence: %s", result.summary)
    else:
        logger.warning("EG6 spec adherence: %s", result.summary)

    return result
