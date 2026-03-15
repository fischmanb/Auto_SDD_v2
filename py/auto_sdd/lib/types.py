"""Shared types for Auto-SDD V2.

GateError is the structured error type used by all new code.
Existing EG modules still use list[str] — migration is separate work.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GateError:
    """Structured gate error with stable code and free-form detail.

    Tests assert on `code` (stable contract).
    `detail` is human-readable and not tested against.
    """
    code: str
    detail: str = ""


@dataclass
class PhaseResult:
    """Result of a pre-build phase (1-6)."""
    phase: str          # "VISION", "SYSTEMS_DESIGN", etc.
    passed: bool = False
    errors: list[GateError] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
