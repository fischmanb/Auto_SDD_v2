"""Tests for EG2: Signal Parse ExecGate."""
from __future__ import annotations

from pathlib import Path

import pytest

from auto_sdd.exec_gates.eg2_signal_parse import (
    ParsedSignals,
    extract_and_validate,
    parse_signals,
    validate_signals,
)


class TestParseSignals:
    def test_basic_extraction(self) -> None:
        output = (
            "Some agent output\n"
            "FEATURE_BUILT: Auth Login\n"
            "SPEC_FILE: .specs/auth.md\n"
            "SOURCE_FILES: src/auth.ts, src/login.ts\n"
        )
        signals = parse_signals(output)
        assert signals.feature_name == "Auth Login"
        assert signals.spec_file == ".specs/auth.md"
        assert signals.source_files == ["src/auth.ts", "src/login.ts"]

    def test_last_occurrence_wins(self) -> None:
        output = (
            "FEATURE_BUILT: First\n"
            "FEATURE_BUILT: Second\n"
        )
        signals = parse_signals(output)
        assert signals.feature_name == "Second"

    def test_missing_signals(self) -> None:
        signals = parse_signals("Just some output with no signals\n")
        assert signals.feature_name == ""
        assert signals.spec_file == ""
        assert signals.source_files == []

    def test_space_separated_source_files(self) -> None:
        output = "SOURCE_FILES: a.ts b.ts c.ts\n"
        signals = parse_signals(output)
        assert signals.source_files == ["a.ts", "b.ts", "c.ts"]

    def test_empty_output(self) -> None:
        signals = parse_signals("")
        assert signals.feature_name == ""

    def test_signal_with_extra_whitespace(self) -> None:
        output = "  FEATURE_BUILT:   Spaced Out  \n"
        signals = parse_signals(output)
        assert signals.feature_name == "Spaced Out"


class TestValidateSignals:
    def test_valid_signals(self, tmp_path: Path) -> None:
        spec = tmp_path / ".specs" / "auth.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("# Auth\n\nImplement login with email and password validation.\n")
        signals = ParsedSignals(
            feature_name="Auth", spec_file=".specs/auth.md",
        )
        result = validate_signals(signals, tmp_path)
        assert result.valid is True
        assert result.errors == []

    def test_missing_feature_name(self, tmp_path: Path) -> None:
        signals = ParsedSignals(spec_file=".specs/auth.md")
        result = validate_signals(signals, tmp_path)
        assert result.valid is False
        assert any(e.code == "MISSING_FEATURE_BUILT" for e in result.errors)

    def test_missing_spec_file(self, tmp_path: Path) -> None:
        signals = ParsedSignals(feature_name="Auth")
        result = validate_signals(signals, tmp_path)
        assert result.valid is False
        assert any(e.code == "MISSING_SPEC_FILE" for e in result.errors)

    def test_spec_file_not_on_disk(self, tmp_path: Path) -> None:
        signals = ParsedSignals(
            feature_name="Auth", spec_file=".specs/nonexistent.md",
        )
        result = validate_signals(signals, tmp_path)
        assert result.valid is False
        assert any(e.code == "SPEC_NOT_FOUND" for e in result.errors)

    def test_spec_file_outside_project(self, tmp_path: Path) -> None:
        # Create a spec file outside project
        outside = tmp_path.parent / "outside-spec.md"
        outside.write_text("# Outside\n")
        signals = ParsedSignals(
            feature_name="Auth",
            spec_file=str(outside),
        )
        result = validate_signals(signals, tmp_path)
        assert result.valid is False
        assert any(e.code == "SPEC_OUTSIDE_PROJECT" for e in result.errors)

    def test_relative_path_resolved_against_project_dir(self, tmp_path: Path) -> None:
        """L-00217: SPEC_FILE must resolve against project_dir, not cwd."""
        spec = tmp_path / ".specs" / "auth.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("# Auth\n\nImplement login with email and password validation.\n")
        signals = ParsedSignals(
            feature_name="Auth", spec_file=".specs/auth.md",
        )
        result = validate_signals(signals, tmp_path)
        assert result.valid is True


class TestExtractAndValidate:
    def test_end_to_end(self, tmp_path: Path) -> None:
        spec = tmp_path / ".specs" / "dashboard.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("# Dashboard\n\nBuild an analytics dashboard with charts and filters.\n")
        # Create source files so SOURCE_FILES validation passes
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "dashboard.tsx").write_text("export default function Dashboard() {}")
        (src_dir / "widgets.tsx").write_text("export default function Widgets() {}")
        output = (
            "Building Dashboard feature...\n"
            "FEATURE_BUILT: Dashboard\n"
            "SPEC_FILE: .specs/dashboard.md\n"
            "SOURCE_FILES: src/dashboard.tsx, src/widgets.tsx\n"
        )
        result = extract_and_validate(output, tmp_path)
        assert result.valid is True
        assert result.feature_name == "Dashboard"
        assert result.spec_file == ".specs/dashboard.md"
        assert len(result.source_files) == 2

    def test_missing_signals_end_to_end(self, tmp_path: Path) -> None:
        result = extract_and_validate("Agent did stuff but no signals\n", tmp_path)
        assert result.valid is False
        assert len(result.errors) >= 2  # Missing both FEATURE_BUILT and SPEC_FILE

    def test_to_dict(self) -> None:
        signals = ParsedSignals(
            feature_name="X", spec_file="x.md",
            source_files=["a.ts"], valid=True, errors=[],
        )
        d = signals.to_dict()
        assert d["feature_name"] == "X"
        assert d["valid"] is True
        assert d["source_files"] == ["a.ts"]


class TestCodeBlockSkip:
    def test_signal_inside_code_block_ignored(self) -> None:
        output = (
            "Here's what I did:\n"
            "```\n"
            "FEATURE_BUILT: FakeSignal\n"
            "```\n"
            "FEATURE_BUILT: RealSignal\n"
        )
        signals = parse_signals(output)
        assert signals.feature_name == "RealSignal"

    def test_all_signals_inside_code_block(self) -> None:
        output = (
            "```\n"
            "FEATURE_BUILT: Trapped\n"
            "SPEC_FILE: trapped.md\n"
            "```\n"
        )
        signals = parse_signals(output)
        assert signals.feature_name == ""
        assert signals.spec_file == ""

    def test_signal_after_code_block_works(self) -> None:
        output = (
            "```python\n"
            "print('hello')\n"
            "```\n"
            "FEATURE_BUILT: AfterBlock\n"
            "SPEC_FILE: .specs/after.md\n"
            "SOURCE_FILES: src/a.ts\n"
        )
        signals = parse_signals(output)
        assert signals.feature_name == "AfterBlock"
        assert signals.spec_file == ".specs/after.md"
        assert signals.source_files == ["src/a.ts"]


class TestSpecContentValidation:
    def test_spec_too_short_fails(self, tmp_path: Path) -> None:
        """Spec files must contain more than 25 characters."""
        spec = tmp_path / ".specs" / "tiny.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("# Tiny")  # 6 chars
        signals = ParsedSignals(
            feature_name="Tiny", spec_file=".specs/tiny.md",
        )
        result = validate_signals(signals, tmp_path)
        assert result.valid is False
        assert any(e.code == "SPEC_TOO_SHORT" for e in result.errors)

    def test_spec_exactly_25_chars_fails(self, tmp_path: Path) -> None:
        spec = tmp_path / ".specs" / "edge.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("a" * 25)  # exactly 25
        signals = ParsedSignals(
            feature_name="Edge", spec_file=".specs/edge.md",
        )
        result = validate_signals(signals, tmp_path)
        assert result.valid is False
        assert any(e.code == "SPEC_TOO_SHORT" for e in result.errors)

    def test_spec_26_chars_passes(self, tmp_path: Path) -> None:
        spec = tmp_path / ".specs" / "ok.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("a" * 26)  # just over
        signals = ParsedSignals(
            feature_name="OK", spec_file=".specs/ok.md",
        )
        result = validate_signals(signals, tmp_path)
        assert result.valid is True


class TestSourceFilesValidation:
    def test_missing_source_file_fails(self, tmp_path: Path) -> None:
        spec = tmp_path / ".specs" / "feat.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("# Feature\n\nA feature with enough content here.\n")
        signals = ParsedSignals(
            feature_name="Feat", spec_file=".specs/feat.md",
            source_files=["src/missing.ts"],
        )
        result = validate_signals(signals, tmp_path)
        assert result.valid is False
        assert any(e.code == "SOURCE_MISSING" for e in result.errors)

    def test_source_file_outside_project_fails(self, tmp_path: Path) -> None:
        spec = tmp_path / ".specs" / "feat.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("# Feature\n\nA feature with enough content here.\n")
        outside = tmp_path.parent / "outside.ts"
        outside.write_text("evil")
        signals = ParsedSignals(
            feature_name="Feat", spec_file=".specs/feat.md",
            source_files=[str(outside)],
        )
        result = validate_signals(signals, tmp_path)
        assert result.valid is False
        assert any(e.code == "SOURCE_OUTSIDE_PROJECT" for e in result.errors)

    def test_valid_source_files_pass(self, tmp_path: Path) -> None:
        spec = tmp_path / ".specs" / "feat.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("# Feature\n\nA feature with enough content here.\n")
        src = tmp_path / "src" / "app.ts"
        src.parent.mkdir()
        src.write_text("export default {}")
        signals = ParsedSignals(
            feature_name="Feat", spec_file=".specs/feat.md",
            source_files=["src/app.ts"],
        )
        result = validate_signals(signals, tmp_path)
        assert result.valid is True
