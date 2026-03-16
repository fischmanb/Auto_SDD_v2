"""Unit tests for pre-build validators.

Tests check error codes (stable contract), not error detail strings.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from auto_sdd.pre_build.validators import (
    validate_vision,
    validate_systems_design,
    validate_design_system,
    validate_personas,
    validate_design_patterns,
    validate_roadmap,
    validate_feature_spec,
    validate_all_specs,
    validate_test_scaffolds,
    _slugify,
    _has_test_function,
    _parse_yaml_frontmatter,
    _check_dependency_cycles,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a minimal project structure."""
    (tmp_path / ".specs").mkdir()
    return tmp_path


# ── VISION tests ─────────────────────────────────────────────────────────────


class TestValidateVision:
    def test_missing_file(self, project: Path):
        errors = validate_vision(project)
        assert len(errors) == 1
        assert errors[0].code == "VISION_MISSING"

    def test_too_short(self, project: Path):
        (project / ".specs" / "vision.md").write_text("hi")
        errors = validate_vision(project)
        assert any(e.code == "VISION_TOO_SHORT" for e in errors)

    def test_missing_section(self, project: Path):
        (project / ".specs" / "vision.md").write_text(
            "# Vision\n## Overview\nSome content here about the app.\n"
            "## Tech Stack\nReact, Node\n"
        )
        errors = validate_vision(project)
        missing = [e for e in errors if e.code == "VISION_MISSING_SECTION"]
        # Should flag target users, key screens, design principles
        assert len(missing) == 3

    def test_valid(self, project: Path):
        content = textwrap.dedent("""\
            # Vision
            ## Overview
            An app for managing tasks.
            ## Target Users
            Developers who need task tracking.
            ## Tech Stack
            React, TypeScript, Node.js
            ## Key Screens
            Dashboard, Settings, Profile
            ## Design Principles
            Simple, fast, accessible.
        """)
        (project / ".specs" / "vision.md").write_text(content)
        errors = validate_vision(project)
        assert errors == []


# ── SYSTEMS DESIGN tests ─────────────────────────────────────────────────────


class TestValidateSystemsDesign:
    def test_missing_file(self, project: Path):
        errors = validate_systems_design(project)
        assert len(errors) == 1
        assert errors[0].code == "SYSTEMS_DESIGN_MISSING"

    def test_valid(self, project: Path):
        content = textwrap.dedent("""\
            # Systems Design
            ## Directory Structure
            src/ for source, tests/ for tests.
            ## State Management
            React context + useReducer.
            ## API Pattern
            REST with fetch wrapper.
            ## Error Handling
            Boundary components + toast notifications.
            ## Naming Conventions
            camelCase for variables, PascalCase for components.
        """)
        (project / ".specs" / "systems-design.md").write_text(content)
        errors = validate_systems_design(project)
        assert errors == []

    def test_missing_sections(self, project: Path):
        (project / ".specs" / "systems-design.md").write_text(
            "# Systems Design\n## Directory Structure\nStuff here.\n"
        )
        errors = validate_systems_design(project)
        missing = [e for e in errors if e.code == "SYSTEMS_DESIGN_MISSING_SECTION"]
        assert len(missing) >= 3


# ── DESIGN SYSTEM tests ──────────────────────────────────────────────────────


class TestValidateDesignSystem:
    def test_missing_file(self, project: Path):
        errors = validate_design_system(project)
        assert len(errors) == 1
        assert errors[0].code == "DESIGN_SYSTEM_MISSING"

    def test_valid(self, project: Path):
        ds_dir = project / ".specs" / "design-system"
        ds_dir.mkdir(parents=True)
        content = textwrap.dedent("""\
            # Design Tokens
            ## Colors
            Primary: #2563eb
            ## Spacing
            Base: 8px
            ## Typography
            Font: Inter, system-ui
        """)
        (ds_dir / "tokens.md").write_text(content)
        errors = validate_design_system(project)
        assert errors == []


# ── ROADMAP tests ────────────────────────────────────────────────────────────


class TestValidateRoadmap:
    def test_missing_file(self, project: Path):
        errors = validate_roadmap(project)
        assert len(errors) == 1
        assert errors[0].code == "ROADMAP_MISSING"

    def test_empty_roadmap(self, project: Path):
        (project / ".specs" / "roadmap.md").write_text(
            "# Roadmap\nNo features yet.\n"
        )
        errors = validate_roadmap(project)
        assert any(e.code == "ROADMAP_EMPTY" for e in errors)

    def test_valid_roadmap(self, project: Path):
        content = textwrap.dedent("""\
            # Roadmap
            | # | Name | Domain | Deps | Complexity | Notes | Status |
            |---|------|--------|------|------------|-------|--------|
            | 1 | Auth | core | - | M | - | ⬜ |
            | 2 | Dashboard | ui | Auth | M | - | ⬜ |
        """)
        (project / ".specs" / "roadmap.md").write_text(content)
        errors = validate_roadmap(project)
        assert errors == []

    def test_bad_status(self, project: Path):
        content = textwrap.dedent("""\
            # Roadmap
            | # | Name | Domain | Deps | Complexity | Notes | Status |
            |---|------|--------|------|------------|-------|--------|
            | 1 | Auth | core | - | M | - | INVALID |
        """)
        (project / ".specs" / "roadmap.md").write_text(content)
        errors = validate_roadmap(project)
        assert any(e.code == "ROADMAP_BAD_STATUS" for e in errors)

    def test_dependency_cycle(self, project: Path):
        content = textwrap.dedent("""\
            # Roadmap
            | # | Name | Domain | Deps | Complexity | Notes | Status |
            |---|------|--------|------|------------|-------|--------|
            | 1 | A | core | B | M | - | ⬜ |
            | 2 | B | core | A | M | - | ⬜ |
        """)
        (project / ".specs" / "roadmap.md").write_text(content)
        errors = validate_roadmap(project)
        assert any(e.code == "ROADMAP_CYCLE" for e in errors)


# ── SPEC-FIRST tests ─────────────────────────────────────────────────────────


class TestValidateFeatureSpec:
    def test_missing_file(self, tmp_path: Path):
        errors = validate_feature_spec(tmp_path / "nonexistent.feature.md")
        assert len(errors) == 1
        assert errors[0].code == "SPEC_MISSING"

    def test_too_short(self, tmp_path: Path):
        p = tmp_path / "short.feature.md"
        p.write_text("hi")
        errors = validate_feature_spec(p)
        assert any(e.code == "SPEC_TOO_SHORT" for e in errors)

    def test_no_frontmatter(self, tmp_path: Path):
        p = tmp_path / "nofm.feature.md"
        p.write_text("# Feature\nGiven something\nWhen action\nThen result\n")
        errors = validate_feature_spec(p)
        assert any(e.code == "SPEC_NO_FRONTMATTER" for e in errors)

    def test_missing_frontmatter_keys(self, tmp_path: Path):
        p = tmp_path / "partial.feature.md"
        p.write_text(textwrap.dedent("""\
            ---
            feature: Test Feature
            ---
            # Test Feature
            Given a user exists
            When they log in
            Then they see the dashboard
        """))
        errors = validate_feature_spec(p)
        missing_keys = [e for e in errors if e.code == "SPEC_FRONTMATTER_MISSING_KEY"]
        # domain and status are missing
        assert len(missing_keys) == 2

    def test_no_gherkin(self, tmp_path: Path):
        p = tmp_path / "nogherkin.feature.md"
        p.write_text(textwrap.dedent("""\
            ---
            feature: No Gherkin
            domain: core
            status: stub
            ---
            # No Gherkin
            This feature has no scenarios at all.
        """))
        errors = validate_feature_spec(p)
        assert any(e.code == "SPEC_NO_GHERKIN" for e in errors)

    def test_valid_spec(self, tmp_path: Path):
        p = tmp_path / "valid.feature.md"
        p.write_text(textwrap.dedent("""\
            ---
            feature: User Auth
            domain: auth
            status: stub
            deps: []
            ---
            # User Auth
            ## Scenario: Login
            Given a registered user
            When they submit valid credentials
            Then they are logged in
        """))
        errors = validate_feature_spec(p)
        assert errors == []


class TestValidateAllSpecs:
    def test_missing_dir(self, project: Path):
        errors = validate_all_specs(project)
        assert any(e.code == "SPECS_DIR_MISSING" for e in errors)

    def test_empty_dir(self, project: Path):
        (project / ".specs" / "features").mkdir(parents=True)
        errors = validate_all_specs(project)
        assert any(e.code == "SPECS_EMPTY" for e in errors)


# ── SCAFFOLD tests ───────────────────────────────────────────────────────────


class TestValidateTestScaffolds:
    def test_missing_test_dir(self, project: Path):
        errors = validate_test_scaffolds(project, ["Auth"])
        assert any(e.code == "TEST_DIR_MISSING" for e in errors)

    def test_missing_scaffold(self, project: Path):
        (project / "tests").mkdir()
        errors = validate_test_scaffolds(project, ["Auth"])
        assert any(e.code == "SCAFFOLD_MISSING" for e in errors)

    def test_scaffold_no_tests(self, project: Path):
        test_dir = project / "tests"
        test_dir.mkdir()
        (test_dir / "test_auth.py").write_text("# empty file\n")
        errors = validate_test_scaffolds(project, ["Auth"])
        assert any(e.code == "SCAFFOLD_NO_TESTS" for e in errors)

    def test_valid_python_scaffold(self, project: Path):
        test_dir = project / "tests"
        test_dir.mkdir()
        (test_dir / "test_auth.py").write_text(
            "def test_login():\n    assert True\n"
        )
        errors = validate_test_scaffolds(project, ["Auth"])
        assert errors == []

    def test_valid_ts_scaffold(self, project: Path):
        test_dir = project / "tests"
        test_dir.mkdir()
        (test_dir / "auth.test.ts").write_text(
            "describe('Auth', () => {\n  it('logs in', () => {});\n});\n"
        )
        errors = validate_test_scaffolds(project, ["Auth"])
        assert errors == []


# ── Helper tests ─────────────────────────────────────────────────────────────


class TestSlugify:
    def test_simple(self):
        assert _slugify("Auth") == "auth"

    def test_spaces(self):
        assert _slugify("User Profile") == "user_profile"

    def test_special_chars(self):
        assert _slugify("Auth: User Signup") == "auth_user_signup"

    def test_leading_trailing(self):
        assert _slugify("  --hello--  ") == "hello"


class TestHasTestFunction:
    def test_python(self):
        assert _has_test_function("def test_login():\n    pass\n")

    def test_js_test(self):
        assert _has_test_function("test('logs in', () => {});\n")

    def test_js_it(self):
        assert _has_test_function("it('logs in', () => {});\n")

    def test_js_describe(self):
        assert _has_test_function("describe('Auth', () => {});\n")

    def test_no_tests(self):
        assert not _has_test_function("# just a comment\nprint('hi')\n")


class TestParseFrontmatter:
    def test_valid(self):
        text = "---\nfeature: Auth\ndomain: core\nstatus: stub\n---\n# Body"
        errors, data = _parse_yaml_frontmatter(text, Path("test.md"))
        assert errors == []
        assert data is not None
        assert data["feature"] == "Auth"
        assert data["domain"] == "core"

    def test_missing_opening(self):
        text = "# No frontmatter\nJust body."
        errors, data = _parse_yaml_frontmatter(text, Path("test.md"))
        assert any(e.code == "SPEC_NO_FRONTMATTER" for e in errors)
        assert data is None

    def test_empty_frontmatter(self):
        text = "---\n---\n# Body"
        errors, data = _parse_yaml_frontmatter(text, Path("test.md"))
        assert any(e.code == "SPEC_EMPTY_FRONTMATTER" for e in errors)


class TestCheckDependencyCycles:
    def test_no_cycle(self):
        features = {
            "A": {"id": 1, "deps": [], "status": "⬜"},
            "B": {"id": 2, "deps": ["A"], "status": "⬜"},
        }
        errors = _check_dependency_cycles(features)
        assert errors == []

    def test_cycle(self):
        features = {
            "A": {"id": 1, "deps": ["B"], "status": "⬜"},
            "B": {"id": 2, "deps": ["A"], "status": "⬜"},
        }
        errors = _check_dependency_cycles(features)
        assert len(errors) == 1
        assert errors[0].code == "ROADMAP_CYCLE"

    def test_three_way_cycle(self):
        features = {
            "A": {"id": 1, "deps": ["C"], "status": "⬜"},
            "B": {"id": 2, "deps": ["A"], "status": "⬜"},
            "C": {"id": 3, "deps": ["B"], "status": "⬜"},
        }
        errors = _check_dependency_cycles(features)
        assert len(errors) == 1
        assert errors[0].code == "ROADMAP_CYCLE"



# ── PERSONAS tests ───────────────────────────────────────────────────────────


class TestValidatePersonas:
    def test_missing_file(self, project: Path):
        errors = validate_personas(project)
        assert len(errors) == 1
        assert errors[0].code == "PERSONAS_MISSING"

    def test_too_short(self, project: Path):
        (project / ".specs" / "personas.md").write_text("hi")
        errors = validate_personas(project)
        assert any(e.code == "PERSONAS_TOO_SHORT" for e in errors)

    def test_missing_sections(self, project: Path):
        (project / ".specs" / "personas.md").write_text(
            "# Personas\n## Sarah — Senior Analyst\n### Role\nSenior CRE Analyst.\n"
        )
        errors = validate_personas(project)
        missing = [e for e in errors if e.code == "PERSONAS_MISSING_SECTION"]
        # Should flag goals, device, density, critical interactions
        assert len(missing) == 4

    def test_valid(self, project: Path):
        content = textwrap.dedent("""\
            # User Personas

            ## Sarah — Senior CRE Analyst
            ### Role
            Senior analyst at a mid-size CRE firm.
            ### Goals
            Quickly assess lease expirations and market positioning.
            ### Device & Environment
            27-inch monitor, dark office, multi-tab workflow.
            ### Data Density Tolerance
            High — wants maximum data on screen.
            ### Critical Interactions
            Sort tables, filter by date range, drill-down into tenant detail.
            ### Frustration Triggers
            Slow load, too much whitespace hiding data.
            ### Accessibility Needs
            High contrast for dark theme.
        """)
        (project / ".specs" / "personas.md").write_text(content)
        errors = validate_personas(project)
        assert errors == []


# ── DESIGN PATTERNS tests ────────────────────────────────────────────────────


class TestValidateDesignPatterns:
    def test_missing_file(self, project: Path):
        errors = validate_design_patterns(project)
        assert len(errors) == 1
        assert errors[0].code == "DESIGN_PATTERNS_MISSING"

    def test_too_short(self, project: Path):
        ds_dir = project / ".specs" / "design-system"
        ds_dir.mkdir(parents=True, exist_ok=True)
        (ds_dir / "patterns.md").write_text("hi")
        errors = validate_design_patterns(project)
        assert any(e.code == "DESIGN_PATTERNS_TOO_SHORT" for e in errors)

    def test_missing_sections(self, project: Path):
        ds_dir = project / ".specs" / "design-system"
        ds_dir.mkdir(parents=True, exist_ok=True)
        (ds_dir / "patterns.md").write_text(
            "# Design Patterns\n## Layout Grid\n12-column grid with 24px gutters.\n"
        )
        errors = validate_design_patterns(project)
        missing = [e for e in errors if e.code == "DESIGN_PATTERNS_MISSING_SECTION"]
        # Should flag: component anatomy, spacing relationships, interaction states, responsive behavior
        assert len(missing) == 4

    def test_valid(self, project: Path):
        ds_dir = project / ".specs" / "design-system"
        ds_dir.mkdir(parents=True, exist_ok=True)
        content = textwrap.dedent("""\
            # Design Patterns
            ## Layout Grid
            12-column grid with spacing-4 gutters.
            ## Component Anatomy
            Cards: p-4 internal padding, rounded, shadow-sm.
            ## Spacing Relationships
            Section-to-section: spacing-8. Card-to-card: spacing-4.
            ## Interaction States
            Default, Hover (emerald-400), Active, Focus, Disabled (opacity-50).
            ## Responsive Behavior
            sm: single column. md: 2 columns. lg: 3 columns.
        """)
        (ds_dir / "patterns.md").write_text(content)
        errors = validate_design_patterns(project)
        assert errors == []


# ── HARDENED SPEC-FIRST tests (token assertions, interaction states) ──────────


class TestFeatureSpecTokenAssertions:
    """Tests for SPEC_NO_TOKEN_ASSERTIONS and SPEC_NO_INTERACTION_STATES."""

    def test_ui_feature_missing_token_assertions(self, tmp_path: Path):
        """UI feature with vague token references fails validation."""
        p = tmp_path / "vague.feature.md"
        p.write_text(textwrap.dedent("""\
            ---
            feature: Property Card
            domain: dashboard
            status: draft
            ---
            # Property Card
            ## Design Token References
            Uses the design tokens from the design system.
            ## Scenario
            Given the dashboard loads
            When the card renders
            Then the card should use the design tokens
            And it looks correct
        """))
        errors = validate_feature_spec(p)
        assert any(e.code == "SPEC_NO_TOKEN_ASSERTIONS" for e in errors)

    def test_ui_feature_missing_interaction_states(self, tmp_path: Path):
        """UI feature without interaction_states in front matter fails."""
        p = tmp_path / "no_states.feature.md"
        p.write_text(textwrap.dedent("""\
            ---
            feature: Tenant Table
            domain: dashboard
            status: draft
            ---
            # Tenant Table
            ## Design Token References
            Colors: emerald-500, zinc-900.
            ## Scenario
            Given data is loaded
            When the table renders
            Then background MUST be `zinc-900`
            And text color MUST be `zinc-100`
            And accent highlights use `emerald-500`
        """))
        errors = validate_feature_spec(p)
        assert any(e.code == "SPEC_NO_INTERACTION_STATES" for e in errors)
        # Token assertions should pass (3 backtick tokens)
        assert not any(e.code == "SPEC_NO_TOKEN_ASSERTIONS" for e in errors)

    def test_ui_feature_with_tokens_and_states_passes(self, tmp_path: Path):
        """UI feature with proper token assertions and states passes."""
        p = tmp_path / "good.feature.md"
        p.write_text(textwrap.dedent("""\
            ---
            feature: Tenant Table
            domain: dashboard
            status: draft
            interaction_states: [default, loading, empty, hover]
            ---
            # Tenant Table
            ## Design Token References
            Colors: emerald-500, zinc-900.
            ## Scenario
            Given data is loaded
            When the table renders
            Then background MUST be `zinc-900`
            And text color MUST be `zinc-100`
            And accent highlights use `emerald-500`
        """))
        errors = validate_feature_spec(p)
        assert errors == []

    def test_non_ui_feature_skips_token_checks(self, tmp_path: Path):
        """Non-UI feature (no design token section) skips token checks."""
        p = tmp_path / "data_loader.feature.md"
        p.write_text(textwrap.dedent("""\
            ---
            feature: Data Loader
            domain: core
            status: draft
            ---
            # Data Loader
            ## Scenario
            Given the app starts
            When the loader reads seed.json
            Then it exposes typed getters for all entities
        """))
        errors = validate_feature_spec(p)
        assert not any(e.code == "SPEC_NO_TOKEN_ASSERTIONS" for e in errors)
        assert not any(e.code == "SPEC_NO_INTERACTION_STATES" for e in errors)

    def test_token_count_boundary(self, tmp_path: Path):
        """Exactly 3 token assertions passes; 2 fails."""
        def make_spec(then_lines: str) -> str:
            return textwrap.dedent(f"""\
                ---
                feature: Widget
                domain: ui
                status: draft
                interaction_states: [default]
                ---
                # Widget
                ## Design Token References
                Uses tokens from design system.
                ## Scenario
                Given the page loads
                When the widget renders
                {then_lines}
            """)

        # 2 tokens — should fail
        p2 = tmp_path / "two.feature.md"
        p2.write_text(make_spec(
            "Then background is `zinc-900`\n"
            "And text is `zinc-100`"
        ))
        errors2 = validate_feature_spec(p2)
        assert any(e.code == "SPEC_NO_TOKEN_ASSERTIONS" for e in errors2)

        # 3 tokens — should pass
        p3 = tmp_path / "three.feature.md"
        p3.write_text(make_spec(
            "Then background is `zinc-900`\n"
            "And text is `zinc-100`\n"
            "And accent is `emerald-500`"
        ))
        errors3 = validate_feature_spec(p3)
        assert not any(e.code == "SPEC_NO_TOKEN_ASSERTIONS" for e in errors3)
