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
        spec.write_text("# Auth spec\n")
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
        assert any("FEATURE_BUILT" in e for e in result.errors)

    def test_missing_spec_file(self, tmp_path: Path) -> None:
        signals = ParsedSignals(feature_name="Auth")
        result = validate_signals(signals, tmp_path)
        assert result.valid is False
        assert any("SPEC_FILE" in e for e in result.errors)

    def test_spec_file_not_on_disk(self, tmp_path: Path) -> None:
        signals = ParsedSignals(
            feature_name="Auth", spec_file=".specs/nonexistent.md",
        )
        result = validate_signals(signals, tmp_path)
        assert result.valid is False
        assert any("does not exist" in e for e in result.errors)

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
        assert any("outside project" in e for e in result.errors)

    def test_relative_path_resolved_against_project_dir(self, tmp_path: Path) -> None:
        """L-00217: SPEC_FILE must resolve against project_dir, not cwd."""
        spec = tmp_path / ".specs" / "auth.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("# Auth\n")
        signals = ParsedSignals(
            feature_name="Auth", spec_file=".specs/auth.md",
        )
        result = validate_signals(signals, tmp_path)
        assert result.valid is True


class TestExtractAndValidate:
    def test_end_to_end(self, tmp_path: Path) -> None:
        spec = tmp_path / ".specs" / "dashboard.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("# Dashboard\n")
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
