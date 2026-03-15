"""Phase 6: RED — deterministic Gherkin-to-test scaffold generator.

No agent involvement. Reads .feature.md files, parses Gherkin steps,
generates scaffold test files with pytest.fail("Not implemented") or
JS test.todo() stubs based on detected project stack (P5).

This is the bridge between spec-driven design intent and the build
agent's job: make pre-existing tests pass.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from auto_sdd.lib.types import GateError, PhaseResult

logger = logging.getLogger(__name__)


# ── Gherkin parser ───────────────────────────────────────────────────────────
#
# Design: format-agnostic keyword extraction.
#
# LLMs emit Gherkin in unpredictable formatting — markdown headers,
# fenced code blocks, indented, plain, mixed. Instead of encoding
# format assumptions into regexes, the parser:
#
#   1. Strips every line to bare text (removes leading #'s, whitespace,
#      list markers, code fence markers)
#   2. Checks if the stripped line starts with a Gherkin keyword
#   3. Builds scenarios from the keyword sequence
#
# This means "### Scenario: X", "  Scenario: X", "- Scenario: X",
# and "```\nScenario: X" all parse identically.

_STEP_KEYWORDS = frozenset({"given", "when", "then", "and", "but"})


def _strip_line(line: str) -> str:
    """Strip markdown/formatting noise from a line, returning bare text.

    Removes: leading whitespace, markdown header markers (# ## ### ####),
    list markers (- * 1.), code fence markers (```), pipe chars from tables.
    """
    s = line.strip()
    # Skip code fence markers entirely
    if s.startswith("```"):
        return ""
    # Strip markdown header prefix
    if s.startswith("#"):
        s = s.lstrip("#").strip()
    # Strip list markers: "- ", "* ", "1. ", "2. " etc.
    if s.startswith(("- ", "* ")):
        s = s[2:].strip()
    elif len(s) >= 3 and s[0].isdigit() and s[1] == "." and s[2] == " ":
        s = s[3:].strip()
    return s


def _is_scenario_header(stripped: str) -> str | None:
    """If stripped line is a Scenario header, return the scenario name.

    Recognizes: "Scenario: Name", "Scenario Outline: Name",
    "Scenario Template: Name" (all case-insensitive on keyword).
    Returns None if not a scenario header.
    """
    low = stripped.lower()
    for prefix in ("scenario outline:", "scenario template:", "scenario:"):
        if low.startswith(prefix):
            name = stripped[len(prefix):].strip()
            return name if name else None
    return None


def _is_step(stripped: str) -> tuple[str, str] | None:
    """If stripped line is a Gherkin step, return (keyword, text).

    Recognizes lines starting with Given/When/Then/And/But (case-insensitive)
    followed by a space and step text.
    """
    parts = stripped.split(None, 1)
    if len(parts) == 2 and parts[0].lower() in _STEP_KEYWORDS:
        return (parts[0].capitalize(), parts[1])
    return None


@dataclass
class GherkinStep:
    """A single Gherkin step."""
    keyword: str   # Given, When, Then, And, But
    text: str


@dataclass
class GherkinScenario:
    """A parsed Gherkin scenario with its steps."""
    name: str
    steps: list[GherkinStep] = field(default_factory=list)


@dataclass
class ParsedSpec:
    """Parsed feature spec with metadata and scenarios."""
    feature_name: str
    domain: str
    scenarios: list[GherkinScenario] = field(default_factory=list)


def parse_feature_spec(spec_path: Path) -> ParsedSpec | None:
    """Parse a .feature.md file into structured data.

    Returns None if the file can't be parsed.
    """
    if not spec_path.exists():
        return None

    text = spec_path.read_text()

    # Extract front matter
    feature_name = spec_path.stem.replace("-", " ").title()
    domain = "general"

    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body = parts[2]
            for line in fm_text.splitlines():
                line = line.strip()
                if line.lower().startswith("feature:"):
                    feature_name = line.split(":", 1)[1].strip()
                elif line.lower().startswith("domain:"):
                    domain = line.split(":", 1)[1].strip()
        else:
            body = text
    else:
        body = text

    # Parse scenarios — format-agnostic keyword extraction
    scenarios: list[GherkinScenario] = []
    current_scenario: GherkinScenario | None = None

    for raw_line in body.splitlines():
        stripped = _strip_line(raw_line)
        if not stripped:
            continue

        # Check for scenario header
        scenario_name = _is_scenario_header(stripped)
        if scenario_name is not None:
            if current_scenario:
                scenarios.append(current_scenario)
            current_scenario = GherkinScenario(name=scenario_name)
            continue

        # Check for step keyword
        step = _is_step(stripped)
        if step is not None and current_scenario is not None:
            current_scenario.steps.append(GherkinStep(
                keyword=step[0],
                text=step[1],
            ))

    if current_scenario:
        scenarios.append(current_scenario)

    return ParsedSpec(
        feature_name=feature_name,
        domain=domain,
        scenarios=scenarios,
    )


# ── Test generators ──────────────────────────────────────────────────────────


def _slugify(name: str) -> str:
    """Convert name to a test-safe identifier."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower().strip())
    return slug.strip("_")


def generate_pytest_scaffold(spec: ParsedSpec) -> str:
    """Generate a pytest scaffold file from parsed spec.

    Each scenario becomes a test function with pytest.fail("Not implemented").
    Steps are included as comments to guide the build agent.
    """
    feature_slug = _slugify(spec.feature_name)
    lines: list[str] = [
        f'"""Tests for {spec.feature_name} — generated from Gherkin spec.',
        '',
        'These tests are scaffold stubs. The build agent\'s job is to',
        'make them pass by implementing the feature.',
        '"""',
        'import pytest',
        '',
        '',
    ]

    for scenario in spec.scenarios:
        test_name = f"test_{_slugify(scenario.name)}"
        lines.append(f"def {test_name}():")
        lines.append(f'    """Scenario: {scenario.name}"""')

        # Add steps as comments
        for step in scenario.steps:
            lines.append(f"    # {step.keyword} {step.text}")

        lines.append('    pytest.fail("Not implemented")')
        lines.append("")
        lines.append("")

    # Remove trailing blank lines
    while lines and lines[-1] == "":
        lines.pop()
    lines.append("")

    return "\n".join(lines)


def generate_vitest_scaffold(spec: ParsedSpec) -> str:
    """Generate a Vitest/Jest scaffold file from parsed spec.

    Each scenario becomes an it.todo() or a test with expect().toFail().
    Steps are included as comments.
    """
    lines: list[str] = [
        f'// Tests for {spec.feature_name} — generated from Gherkin spec.',
        '//',
        "// These tests are scaffold stubs. The build agent's job is to",
        "// make them pass by implementing the feature.",
        '',
        "import { describe, it, expect } from 'vitest';",
        '',
        f"describe('{spec.feature_name}', () => {{",
    ]

    for scenario in spec.scenarios:
        lines.append(f"  it('{scenario.name}', () => {{")

        for step in scenario.steps:
            lines.append(f"    // {step.keyword} {step.text}")

        lines.append("    expect(true).toBe(false); // Not implemented")
        lines.append("  });")
        lines.append("")

    # Remove trailing blank line inside describe
    while lines and lines[-1] == "":
        lines.pop()
    lines.append("});")
    lines.append("")

    return "\n".join(lines)


# ── Stack detection (P5) ─────────────────────────────────────────────────────


def detect_test_stack(project_dir: Path) -> str:
    """Detect whether to generate pytest or vitest scaffolds.

    Returns "pytest" or "vitest" based on project markers.
    """
    if (project_dir / "package.json").exists():
        return "vitest"
    return "pytest"


def _test_dir_for_stack(project_dir: Path, stack: str) -> Path:
    """Return the test directory based on stack."""
    if stack == "vitest":
        # Prefer src/__tests__/ if src/ exists, else tests/
        src_tests = project_dir / "src" / "__tests__"
        if (project_dir / "src").is_dir():
            return src_tests
        return project_dir / "tests"
    return project_dir / "tests"


# ── Entry point ──────────────────────────────────────────────────────────────


def run_phase_red(project_dir: Path) -> PhaseResult:
    """Generate test scaffold files from Gherkin specs.

    Deterministic — no agent, no LLM. Reads .feature.md files,
    parses Gherkin, writes test stubs.
    """
    spec_dir = project_dir / ".specs" / "features"
    if not spec_dir.is_dir():
        return PhaseResult(
            phase="RED",
            passed=False,
            errors=[GateError("SPECS_DIR_MISSING", f"{spec_dir} does not exist")],
        )

    spec_files = list(spec_dir.rglob("*.feature.md"))
    if not spec_files:
        return PhaseResult(
            phase="RED",
            passed=False,
            errors=[GateError("SPECS_EMPTY", "No .feature.md files to scaffold")],
        )

    stack = detect_test_stack(project_dir)
    test_dir = _test_dir_for_stack(project_dir, stack)
    test_dir.mkdir(parents=True, exist_ok=True)

    errors: list[GateError] = []
    generated: list[str] = []

    for spec_path in spec_files:
        parsed = parse_feature_spec(spec_path)
        if parsed is None:
            errors.append(GateError(
                "SPEC_PARSE_FAILED",
                f"Could not parse {spec_path}",
            ))
            continue

        if not parsed.scenarios:
            errors.append(GateError(
                "SPEC_NO_SCENARIOS",
                f"{spec_path}: no Gherkin scenarios found",
            ))
            continue

        slug = _slugify(parsed.feature_name)

        if stack == "pytest":
            content = generate_pytest_scaffold(parsed)
            filename = f"test_{slug}.py"
        else:
            content = generate_vitest_scaffold(parsed)
            filename = f"{slug}.test.ts"

        out_path = test_dir / filename
        out_path.write_text(content)
        generated.append(str(out_path.relative_to(project_dir)))

        logger.info(
            "RED: generated %s (%d scenarios)", filename, len(parsed.scenarios),
        )

    if errors:
        return PhaseResult(phase="RED", passed=False, errors=errors)

    logger.info("RED: generated %d test scaffolds (%s)", len(generated), stack)
    return PhaseResult(
        phase="RED",
        passed=True,
        artifacts={"generated_files": generated, "stack": stack},
    )
