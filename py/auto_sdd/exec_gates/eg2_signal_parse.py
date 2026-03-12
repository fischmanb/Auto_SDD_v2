"""EG2: Signal Parse ExecGate — mechanical signal extraction.

Extracts FEATURE_BUILT / SPEC_FILE / SOURCE_FILES from agent output.
No agent self-assessment accepted. Either the signals are present and
the referenced files exist on disk, or the build failed. Binary,
deterministic.

This replaces the _parse_signal / _validate_required_signals functions
from the current build_loop.py with a structured result type and
stricter validation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Result types ─────────────────────────────────────────────────────────────


@dataclass
class ParsedSignals:
    """Structured result of signal extraction from agent output.

    All fields are populated by mechanical parsing — no inference,
    no fallback, no agent self-assessment.
    """

    feature_name: str = ""
    spec_file: str = ""
    source_files: list[str] = field(default_factory=list)

    # Validation results (populated by validate())
    valid: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "feature_name": self.feature_name,
            "spec_file": self.spec_file,
            "source_files": self.source_files,
            "valid": self.valid,
            "errors": self.errors,
        }


# ── Parsing ──────────────────────────────────────────────────────────────────

# Signal protocol (L-00028): grep-parseable signals emitted by the agent.
# Format: SIGNAL_NAME: value
# The parser is strict — misformatted signal = build failure, not silent skip.

_SIGNAL_PREFIXES = {
    "FEATURE_BUILT": "feature_name",
    "SPEC_FILE": "spec_file",
    "SOURCE_FILES": "source_files",
}


def parse_signals(agent_output: str) -> ParsedSignals:
    """Extract signals from agent output. Pure string parsing — no inference.

    Scans for lines matching the signal protocol:
        FEATURE_BUILT: <feature name>
        SPEC_FILE: <path to spec file>
        SOURCE_FILES: <comma-separated file paths>

    If a signal appears multiple times, the LAST occurrence wins
    (agent may emit intermediate signals before the final one).

    Returns a ParsedSignals with raw extracted values. Call validate()
    to check whether the signals are sufficient and files exist.
    """
    result = ParsedSignals()

    for line in agent_output.splitlines():
        stripped = line.strip()
        for prefix, attr in _SIGNAL_PREFIXES.items():
            signal_prefix = f"{prefix}:"
            if stripped.startswith(signal_prefix):
                value = stripped[len(signal_prefix):].strip()
                if attr == "source_files":
                    # SOURCE_FILES can be comma-separated or space-separated
                    files = [
                        f.strip()
                        for f in value.replace(",", " ").split()
                        if f.strip()
                    ]
                    result.source_files = files
                else:
                    setattr(result, attr, value)

    return result


# ── Validation ───────────────────────────────────────────────────────────────


def validate_signals(
    signals: ParsedSignals,
    project_dir: Path,
) -> ParsedSignals:
    """Validate parsed signals against disk state.

    Checks:
        1. FEATURE_BUILT is present and non-empty
        2. SPEC_FILE is present and exists on disk
        3. SPEC_FILE resolves within project_dir (not outside)

    Mutates signals.valid and signals.errors, then returns signals
    for chaining.
    """
    errors: list[str] = []

    # 1. FEATURE_BUILT is required
    if not signals.feature_name:
        errors.append("Missing required signal: FEATURE_BUILT")

    # 2. SPEC_FILE is required
    if not signals.spec_file:
        errors.append("Missing required signal: SPEC_FILE")
    else:
        # Resolve relative paths against project_dir (L-00217: not loop cwd)
        spec_path = Path(signals.spec_file)
        if not spec_path.is_absolute():
            spec_path = project_dir / spec_path

        if not spec_path.exists():
            errors.append(
                f"SPEC_FILE does not exist on disk: {signals.spec_file} "
                f"(resolved: {spec_path})"
            )
        else:
            # Check containment
            try:
                spec_path.resolve().relative_to(project_dir.resolve())
            except ValueError:
                errors.append(
                    f"SPEC_FILE resolves outside project: {spec_path}"
                )

    signals.errors = errors
    signals.valid = len(errors) == 0

    if errors:
        for err in errors:
            logger.warning("EG2 signal validation: %s", err)
    else:
        logger.debug(
            "EG2 signals valid: feature=%s, spec=%s, sources=%d",
            signals.feature_name,
            signals.spec_file,
            len(signals.source_files),
        )

    return signals


# ── Convenience ──────────────────────────────────────────────────────────────


def extract_and_validate(
    agent_output: str,
    project_dir: Path,
) -> ParsedSignals:
    """Parse + validate in one call. The typical usage pattern."""
    signals = parse_signals(agent_output)
    return validate_signals(signals, project_dir)
