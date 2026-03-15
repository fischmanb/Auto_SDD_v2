"""Unit tests for Phase 6: RED — deterministic Gherkin-to-test scaffold generator."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from auto_sdd.pre_build.phase_red import (
    parse_feature_spec,
    generate_pytest_scaffold,
    generate_vitest_scaffold,
    detect_test_stack,
    run_phase_red,
    _slugify,
    ParsedSpec,
    GherkinScenario,
    GherkinStep,
)


VALID_SPEC = textwrap.dedent("""\
    ---
    feature: User Auth
    domain: auth
    status: stub
    ---
    # User Auth

    ### Scenario: Successful login
    Given a registered user
    When they submit valid credentials
    Then they are redirected to the dashboard
    And they see a welcome message
""")

MULTI_SCENARIO_SPEC = textwrap.dedent("""\
    ---
    feature: Shopping Cart
    domain: commerce
    status: stub
    ---
    # Shopping Cart

    ### Scenario: Add item to cart
    Given an empty cart
    When the user adds a product
    Then the cart shows 1 item

    ### Scenario: Remove item from cart
    Given a cart with 1 item
    When the user removes the item
    Then the cart is empty

    ### Scenario: Quantity update
    Given a cart with 1 item
    When the user changes quantity to 3
    Then the cart shows quantity 3
""")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".specs" / "features" / "auth").mkdir(parents=True)
    return tmp_path


# ── Parser tests ─────────────────────────────────────────────────────────────


class TestParseFeatureSpec:
    def test_basic_parse(self, tmp_path: Path):
        p = tmp_path / "auth.feature.md"
        p.write_text(VALID_SPEC)
        result = parse_feature_spec(p)
        assert result is not None
        assert result.feature_name == "User Auth"
        assert result.domain == "auth"
        assert len(result.scenarios) == 1
        assert result.scenarios[0].name == "Successful login"
        assert len(result.scenarios[0].steps) == 4

    def test_multi_scenario(self, tmp_path: Path):
        p = tmp_path / "cart.feature.md"
        p.write_text(MULTI_SCENARIO_SPEC)
        result = parse_feature_spec(p)
        assert result is not None
        assert result.feature_name == "Shopping Cart"
        assert len(result.scenarios) == 3
        assert result.scenarios[0].name == "Add item to cart"
        assert result.scenarios[2].name == "Quantity update"

    def test_step_keywords(self, tmp_path: Path):
        p = tmp_path / "auth.feature.md"
        p.write_text(VALID_SPEC)
        result = parse_feature_spec(p)
        steps = result.scenarios[0].steps
        assert steps[0].keyword == "Given"
        assert steps[1].keyword == "When"
        assert steps[2].keyword == "Then"
        assert steps[3].keyword == "And"

    def test_missing_file(self, tmp_path: Path):
        result = parse_feature_spec(tmp_path / "nonexistent.md")
        assert result is None

    def test_no_frontmatter(self, tmp_path: Path):
        p = tmp_path / "nofm.feature.md"
        p.write_text("# Feature\n### Scenario: Test\nGiven something\n")
        result = parse_feature_spec(p)
        assert result is not None
        assert len(result.scenarios) == 1

    def test_no_scenarios(self, tmp_path: Path):
        p = tmp_path / "empty.feature.md"
        p.write_text("---\nfeature: Empty\ndomain: core\n---\n# Empty\nNo scenarios.\n")
        result = parse_feature_spec(p)
        assert result is not None
        assert len(result.scenarios) == 0


# ── Generator tests ──────────────────────────────────────────────────────────


class TestGeneratePytestScaffold:
    def test_single_scenario(self, tmp_path: Path):
        p = tmp_path / "auth.feature.md"
        p.write_text(VALID_SPEC)
        spec = parse_feature_spec(p)
        output = generate_pytest_scaffold(spec)
        assert "def test_successful_login():" in output
        assert 'pytest.fail("Not implemented")' in output
        assert "# Given a registered user" in output
        assert "# When they submit valid credentials" in output

    def test_multi_scenario(self, tmp_path: Path):
        p = tmp_path / "cart.feature.md"
        p.write_text(MULTI_SCENARIO_SPEC)
        spec = parse_feature_spec(p)
        output = generate_pytest_scaffold(spec)
        assert "def test_add_item_to_cart():" in output
        assert "def test_remove_item_from_cart():" in output
        assert "def test_quantity_update():" in output
        # Should have 3 pytest.fail calls
        assert output.count('pytest.fail("Not implemented")') == 3

    def test_import_present(self, tmp_path: Path):
        p = tmp_path / "auth.feature.md"
        p.write_text(VALID_SPEC)
        spec = parse_feature_spec(p)
        output = generate_pytest_scaffold(spec)
        assert "import pytest" in output


class TestGenerateVitestScaffold:
    def test_single_scenario(self, tmp_path: Path):
        p = tmp_path / "auth.feature.md"
        p.write_text(VALID_SPEC)
        spec = parse_feature_spec(p)
        output = generate_vitest_scaffold(spec)
        assert "describe('User Auth'" in output
        assert "it('Successful login'" in output
        assert "expect(true).toBe(false)" in output
        assert "// Given a registered user" in output

    def test_multi_scenario(self, tmp_path: Path):
        p = tmp_path / "cart.feature.md"
        p.write_text(MULTI_SCENARIO_SPEC)
        spec = parse_feature_spec(p)
        output = generate_vitest_scaffold(spec)
        assert "it('Add item to cart'" in output
        assert "it('Remove item from cart'" in output
        assert "it('Quantity update'" in output
        assert output.count("expect(true).toBe(false)") == 3

    def test_import_present(self, tmp_path: Path):
        p = tmp_path / "auth.feature.md"
        p.write_text(VALID_SPEC)
        spec = parse_feature_spec(p)
        output = generate_vitest_scaffold(spec)
        assert "import { describe, it, expect } from 'vitest'" in output


# ── Stack detection tests ────────────────────────────────────────────────────


class TestDetectTestStack:
    def test_python_default(self, tmp_path: Path):
        assert detect_test_stack(tmp_path) == "pytest"

    def test_node_project(self, tmp_path: Path):
        (tmp_path / "package.json").write_text("{}")
        assert detect_test_stack(tmp_path) == "vitest"


# ── Integration tests (run_phase_red) ────────────────────────────────────────


class TestRunPhaseRed:
    def test_no_specs_dir(self, tmp_path: Path):
        result = run_phase_red(tmp_path)
        assert not result.passed
        assert any(e.code == "SPECS_DIR_MISSING" for e in result.errors)

    def test_empty_specs_dir(self, tmp_path: Path):
        (tmp_path / ".specs" / "features").mkdir(parents=True)
        result = run_phase_red(tmp_path)
        assert not result.passed
        assert any(e.code == "SPECS_EMPTY" for e in result.errors)

    def test_generates_pytest(self, project: Path):
        (project / ".specs" / "features" / "auth" / "login.feature.md").write_text(
            VALID_SPEC,
        )
        result = run_phase_red(project)
        assert result.passed
        assert (project / "tests" / "test_user_auth.py").exists()
        content = (project / "tests" / "test_user_auth.py").read_text()
        assert "def test_successful_login():" in content

    def test_generates_vitest(self, project: Path):
        (project / "package.json").write_text("{}")
        (project / "src").mkdir()
        (project / ".specs" / "features" / "auth" / "login.feature.md").write_text(
            VALID_SPEC,
        )
        result = run_phase_red(project)
        assert result.passed
        test_file = project / "src" / "__tests__" / "user_auth.test.ts"
        assert test_file.exists()
        content = test_file.read_text()
        assert "describe('User Auth'" in content

    def test_spec_no_scenarios(self, project: Path):
        (project / ".specs" / "features" / "auth" / "empty.feature.md").write_text(
            "---\nfeature: Empty\ndomain: auth\n---\n# Empty\nNo scenarios here.\n",
        )
        result = run_phase_red(project)
        assert not result.passed
        assert any(e.code == "SPEC_NO_SCENARIOS" for e in result.errors)

    def test_multi_spec_generation(self, project: Path):
        (project / ".specs" / "features" / "auth" / "login.feature.md").write_text(
            VALID_SPEC,
        )
        commerce_dir = project / ".specs" / "features" / "commerce"
        commerce_dir.mkdir(parents=True)
        (commerce_dir / "cart.feature.md").write_text(MULTI_SCENARIO_SPEC)

        result = run_phase_red(project)
        assert result.passed
        assert (project / "tests" / "test_user_auth.py").exists()
        assert (project / "tests" / "test_shopping_cart.py").exists()
        # Shopping cart should have 3 test functions
        cart_content = (project / "tests" / "test_shopping_cart.py").read_text()
        assert cart_content.count('pytest.fail("Not implemented")') == 3
