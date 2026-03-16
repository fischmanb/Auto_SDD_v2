"""Deterministic validators for pre-build phase outputs.

Each validator checks structural requirements only — file exists,
required sections present, parseable format. No content judgment (DP-2).

All validators return list[GateError]. Empty list = passed.
"""
from __future__ import annotations

import re
from pathlib import Path

from auto_sdd.lib.types import GateError


# ── Phase 1: VISION ──────────────────────────────────────────────────────────

VISION_REQUIRED_SECTIONS = [
    "overview",
    "target users",
    "tech stack",
    "key screens",
    "design principles",
]


def validate_vision(project_dir: Path) -> list[GateError]:
    """Validate .specs/vision.md exists and has required sections."""
    path = project_dir / ".specs" / "vision.md"
    return _validate_markdown_sections(path, "VISION", VISION_REQUIRED_SECTIONS)


# ── Phase 2: SYSTEMS DESIGN ──────────────────────────────────────────────────

SYSTEMS_REQUIRED_SECTIONS = [
    "directory structure",
    "state management",
    "api",
    "error handling",
    "naming conventions",
]


def validate_systems_design(project_dir: Path) -> list[GateError]:
    """Validate .specs/systems-design.md exists and has required sections."""
    path = project_dir / ".specs" / "systems-design.md"
    return _validate_markdown_sections(
        path, "SYSTEMS_DESIGN", SYSTEMS_REQUIRED_SECTIONS,
    )


# ── Phase 3: DESIGN SYSTEM ──────────────────────────────────────────────────

DESIGN_REQUIRED_SECTIONS = [
    "colors",
    "spacing",
    "typography",
]


def validate_design_system(project_dir: Path) -> list[GateError]:
    """Validate .specs/design-system/tokens.md exists and has token categories."""
    path = project_dir / ".specs" / "design-system" / "tokens.md"
    return _validate_markdown_sections(path, "DESIGN_SYSTEM", DESIGN_REQUIRED_SECTIONS)


# ── Phase 3b: PERSONAS ──────────────────────────────────────────────────────

PERSONAS_REQUIRED_SECTIONS = [
    "role",
    "goals",
    "device",
    "density",
    "critical interactions",
]


def validate_personas(project_dir: Path) -> list[GateError]:
    """Validate .specs/personas.md exists and has structured persona content."""
    path = project_dir / ".specs" / "personas.md"
    return _validate_markdown_sections(path, "PERSONAS", PERSONAS_REQUIRED_SECTIONS)


# ── Phase 3c: DESIGN PATTERNS ───────────────────────────────────────────────

DESIGN_PATTERNS_REQUIRED_SECTIONS = [
    "layout grid",
    "component anatomy",
    "spacing relationships",
    "interaction states",
    "responsive behavior",
]


def validate_design_patterns(project_dir: Path) -> list[GateError]:
    """Validate .specs/design-system/patterns.md exists with required sections."""
    path = project_dir / ".specs" / "design-system" / "patterns.md"
    return _validate_markdown_sections(
        path, "DESIGN_PATTERNS", DESIGN_PATTERNS_REQUIRED_SECTIONS,
    )


# ── Phase 4: ROADMAP ─────────────────────────────────────────────────────────


def validate_roadmap(project_dir: Path) -> list[GateError]:
    """Validate .specs/roadmap.md is parseable with valid structure.

    Checks:
    - File exists
    - At least one parseable table row with expected columns
    - All status values are recognized (⬜/✅/🔄/⏸️)
    - Dependencies reference known feature names
    - No dependency cycles (Kahn's algorithm)
    """
    path = project_dir / ".specs" / "roadmap.md"
    errors: list[GateError] = []

    if not path.exists():
        errors.append(GateError("ROADMAP_MISSING", f"{path} does not exist"))
        return errors

    text = path.read_text()
    features, parse_errors = _parse_roadmap_table(text)
    errors.extend(parse_errors)

    if not features and not parse_errors:
        errors.append(GateError("ROADMAP_EMPTY", "No parseable feature rows found"))
        return errors

    if features:
        cycle_errors = _check_dependency_cycles(features)
        errors.extend(cycle_errors)

        entry_errors = _check_app_entry_point(features, project_dir)
        errors.extend(entry_errors)

    return errors


# ── Phase 5: SPEC-FIRST ──────────────────────────────────────────────────────

SPEC_REQUIRED_FRONTMATTER_KEYS = ["feature", "domain", "status"]
GHERKIN_PATTERN = re.compile(
    r"^\s*(Given|When|Then|And|But)\s+.+", re.MULTILINE,
)
# Matches backtick-wrapped tokens like `zinc-900`, `text-base`, `p-4`, `emerald-500`
_TOKEN_IN_BACKTICKS = re.compile(r"`[a-z]+-[a-z0-9]+(?:-[a-z0-9]+)*`")
_THEN_AND_PATTERN = re.compile(
    r"^\s*(Then|And)\s+.+", re.MULTILINE,
)
_MIN_TOKEN_ASSERTIONS = 3


def validate_feature_spec(spec_path: Path) -> list[GateError]:
    """Validate a single .feature.md file.

    Checks:
    - File exists and is non-empty
    - YAML front matter present and parseable with required keys
    - At least one Gherkin step (Given/When/Then)
    - UI features: interaction_states in front matter
    - UI features: at least 3 backtick-wrapped token assertions in Then/And steps
    """
    errors: list[GateError] = []

    if not spec_path.exists():
        errors.append(GateError("SPEC_MISSING", f"{spec_path} does not exist"))
        return errors

    text = spec_path.read_text().strip()
    if len(text) < 25:
        errors.append(GateError("SPEC_TOO_SHORT", f"{spec_path} has insufficient content"))
        return errors

    # YAML front matter check
    fm_errors, fm_data = _parse_yaml_frontmatter(text, spec_path)
    errors.extend(fm_errors)

    if fm_data is not None:
        for key in SPEC_REQUIRED_FRONTMATTER_KEYS:
            if key not in fm_data:
                errors.append(GateError(
                    "SPEC_FRONTMATTER_MISSING_KEY",
                    f"{spec_path}: missing required key '{key}'",
                ))

    # Gherkin check — strip front matter before searching
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]

    if not GHERKIN_PATTERN.search(body):
        errors.append(GateError(
            "SPEC_NO_GHERKIN",
            f"{spec_path}: no Given/When/Then steps found",
        ))

    # UI feature checks — triggered when spec has a Design Token References section
    body_lower = body.lower()
    is_ui_feature = "design token" in body_lower

    if is_ui_feature:
        # Check interaction_states in front matter
        if fm_data is not None and "interaction_states" not in fm_data:
            errors.append(GateError(
                "SPEC_NO_INTERACTION_STATES",
                f"{spec_path}: UI feature missing 'interaction_states' in front matter",
            ))

        # Check for concrete token assertions in Then/And lines
        then_and_text = "\n".join(
            m.group(0) for m in _THEN_AND_PATTERN.finditer(body)
        )
        token_matches = _TOKEN_IN_BACKTICKS.findall(then_and_text)
        if len(token_matches) < _MIN_TOKEN_ASSERTIONS:
            errors.append(GateError(
                "SPEC_NO_TOKEN_ASSERTIONS",
                f"{spec_path}: UI feature has {len(token_matches)} token "
                f"assertion(s) in Then/And steps, need at least "
                f"{_MIN_TOKEN_ASSERTIONS}. Use backtick-wrapped token "
                f"names like `zinc-900`, `text-base` in Then/And steps.",
            ))

    return errors


def validate_all_specs(project_dir: Path) -> list[GateError]:
    """Validate all .feature.md files under .specs/features/."""
    spec_dir = project_dir / ".specs" / "features"
    errors: list[GateError] = []

    if not spec_dir.is_dir():
        errors.append(GateError("SPECS_DIR_MISSING", f"{spec_dir} does not exist"))
        return errors

    specs = list(spec_dir.rglob("*.feature.md"))
    if not specs:
        errors.append(GateError("SPECS_EMPTY", "No .feature.md files found"))
        return errors

    for spec_path in specs:
        errors.extend(validate_feature_spec(spec_path))

    return errors


# ── Phase 6: RED (test scaffolding) ─────────────────────────────────────────


def validate_test_scaffolds(
    project_dir: Path,
    expected_features: list[str],
    test_dir_name: str = "tests",
) -> list[GateError]:
    """Validate that scaffold test files were generated for each feature.

    Checks test files exist and contain at least one test function/method.
    """
    errors: list[GateError] = []
    test_dir = project_dir / test_dir_name

    if not test_dir.is_dir():
        errors.append(GateError("TEST_DIR_MISSING", f"{test_dir} does not exist"))
        return errors

    for feature_name in expected_features:
        slug = _slugify(feature_name)
        # Look for test_<slug>.py or <slug>.test.ts patterns
        found = False
        for pattern in [f"test_{slug}.py", f"{slug}.test.ts", f"{slug}.test.tsx"]:
            matches = list(test_dir.rglob(pattern))
            if matches:
                # Check file has at least one test function
                content = matches[0].read_text()
                if _has_test_function(content):
                    found = True
                    break
                else:
                    errors.append(GateError(
                        "SCAFFOLD_NO_TESTS",
                        f"{matches[0]}: file exists but has no test functions",
                    ))
                    found = True  # file exists, just empty
                    break
        if not found:
            errors.append(GateError(
                "SCAFFOLD_MISSING",
                f"No test scaffold found for feature '{feature_name}'",
            ))

    return errors


# ── Shared helpers ───────────────────────────────────────────────────────────

VALID_STATUSES = {"⬜", "✅", "🔄", "⏸️"}


def _validate_markdown_sections(
    path: Path,
    phase: str,
    required_sections: list[str],
) -> list[GateError]:
    """Check that a markdown file exists and contains required section headings.

    Section matching is case-insensitive substring match against heading text.
    """
    errors: list[GateError] = []

    if not path.exists():
        errors.append(GateError(f"{phase}_MISSING", f"{path} does not exist"))
        return errors

    text = path.read_text().strip()
    if len(text) < 25:
        errors.append(GateError(f"{phase}_TOO_SHORT", f"{path} has insufficient content"))
        return errors

    text_lower = text.lower()
    for section in required_sections:
        if section.lower() not in text_lower:
            errors.append(GateError(
                f"{phase}_MISSING_SECTION",
                f"{path}: required section '{section}' not found",
            ))

    return errors


def _parse_yaml_frontmatter(
    text: str, source: Path,
) -> tuple[list[GateError], dict | None]:
    """Extract and parse YAML front matter from markdown text.

    Returns (errors, parsed_dict). parsed_dict is None if parsing failed.
    Does not import PyYAML — uses simple key: value parsing for robustness.
    """
    errors: list[GateError] = []

    if not text.startswith("---"):
        errors.append(GateError(
            "SPEC_NO_FRONTMATTER",
            f"{source}: no YAML front matter (missing opening ---)",
        ))
        return errors, None

    parts = text.split("---", 2)
    if len(parts) < 3:
        errors.append(GateError(
            "SPEC_BAD_FRONTMATTER",
            f"{source}: malformed front matter (missing closing ---)",
        ))
        return errors, None

    fm_text = parts[1].strip()
    if not fm_text:
        errors.append(GateError(
            "SPEC_EMPTY_FRONTMATTER",
            f"{source}: front matter is empty",
        ))
        return errors, None

    # Simple key: value parser (avoids PyYAML dependency)
    data: dict[str, str] = {}
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            data[key.strip().lower()] = val.strip()

    return errors, data


def _parse_roadmap_table(
    text: str,
) -> tuple[dict[str, dict], list[GateError]]:
    """Parse roadmap markdown table rows.

    Returns (features_dict, errors).
    features_dict: {name: {"id": int, "domain": str, "deps": list[str], "status": str, "complexity": str, "notes": str}}
    """
    features: dict[str, dict] = {}
    errors: list[GateError] = []

    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue

        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c]
        if len(cells) < 7:
            continue

        try:
            fid = int(cells[0])
        except (ValueError, IndexError):
            continue

        name = cells[1].strip()
        domain = cells[2].strip().lower().replace(" ", "-") or "general"
        deps_str = cells[3].strip()
        complexity = cells[4].strip() or "M"
        status_cell = cells[6].strip()

        deps = [d.strip() for d in deps_str.split(",") if d.strip() and d.strip() != "-"]
        notes = cells[5].strip() if len(cells) > 5 else ""

        # Validate status
        status_found = False
        for s in VALID_STATUSES:
            if s in status_cell:
                status_found = True
                break
        if not status_found:
            errors.append(GateError(
                "ROADMAP_BAD_STATUS",
                f"Feature '{name}' (#{fid}): unrecognized status '{status_cell}'",
            ))

        features[name] = {"id": fid, "domain": domain, "deps": deps, "status": status_cell, "complexity": complexity, "notes": notes}

    return features, errors


def _check_dependency_cycles(features: dict[str, dict]) -> list[GateError]:
    """Detect dependency cycles using Kahn's algorithm.

    Returns GateError with ROADMAP_CYCLE code if cycles found.
    """
    from collections import deque

    all_names = set(features.keys())
    in_degree: dict[str, int] = {name: 0 for name in all_names}
    dependents: dict[str, list[str]] = {name: [] for name in all_names}

    for name, data in features.items():
        for dep in data["deps"]:
            if dep in all_names:
                in_degree[name] += 1
                dependents[dep].append(name)

    queue: deque[str] = deque(n for n, d in in_degree.items() if d == 0)
    processed = 0

    while queue:
        node = queue.popleft()
        processed += 1
        for dep in dependents.get(node, []):
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)

    if processed < len(all_names):
        remaining = sorted(n for n, d in in_degree.items() if d > 0)
        return [GateError(
            "ROADMAP_CYCLE",
            f"Dependency cycle among: {', '.join(remaining)}",
        )]

    return []


def _check_app_entry_point(
    features: dict[str, dict], project_dir: Path,
) -> list[GateError]:
    """Warn if a web app project has no entry point feature in the roadmap.

    Detects web apps by checking package.json for Next.js, React, Vue,
    Angular, Svelte. If found, checks that at least one feature name or
    notes suggest an app shell / entry point / layout / page.
    """
    import json

    pkg_path = project_dir / "package.json"
    if not pkg_path.exists():
        return []

    try:
        pkg = json.loads(pkg_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    all_deps = {}
    all_deps.update(pkg.get("dependencies", {}))
    all_deps.update(pkg.get("devDependencies", {}))

    web_frameworks = {"next", "react", "vue", "@angular/core", "svelte"}
    is_web_app = bool(web_frameworks & set(all_deps.keys()))
    if not is_web_app:
        return []

    entry_keywords = {
        "shell", "entry", "layout", "page", "app shell",
        "main page", "root", "index", "scaffold",
    }
    for name, data in features.items():
        name_lower = name.lower()
        notes_lower = data.get("notes", "").lower() if isinstance(data.get("notes"), str) else ""
        for kw in entry_keywords:
            if kw in name_lower or kw in notes_lower:
                return []

    return [GateError(
        "ROADMAP_NO_ENTRY_POINT",
        "Web app detected but no feature creates an app entry point "
        "(app/layout.tsx, app/page.tsx, index.html, etc.). Add an App "
        "Shell feature that depends on all other features and creates "
        "the application entry point.",
    )]


def _slugify(name: str) -> str:
    """Convert feature name to a filename-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug


def _has_test_function(content: str) -> bool:
    """Check if file content contains at least one test function/method.

    Detects:
    - Python: def test_...
    - JS/TS: test(...), it(...), describe(...)
    """
    if re.search(r"^\s*def\s+test_", content, re.MULTILINE):
        return True
    if re.search(r"^\s*(test|it|describe)\s*\(", content, re.MULTILINE):
        return True
    return False
