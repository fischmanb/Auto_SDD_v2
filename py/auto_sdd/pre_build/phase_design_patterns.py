"""Phase 3c: DESIGN PATTERNS — generate .specs/design-system/patterns.md.

Runs after personas (phase 3b). Produces structured layout rules,
component anatomy, interaction states, spacing relationships, and
responsive behavior — all grounded in tokens and personas.

This is the bridge between raw token values and how the build agent
applies them. Specs (phase 5) and the build agent reference this
document to produce consistent, high-quality UI.
"""
from __future__ import annotations

from pathlib import Path

from auto_sdd.lib.model_config import ModelConfig
from auto_sdd.lib.types import PhaseResult
from auto_sdd.pre_build.runner import run_phase
from auto_sdd.pre_build.prompts import (
    design_patterns_system_prompt,
    design_patterns_user_prompt,
)
from auto_sdd.pre_build.validators import validate_design_patterns


def run_phase_design_patterns(
    config: ModelConfig,
    project_dir: Path,
    max_attempts: int = 2,
) -> PhaseResult:
    """Generate .specs/design-system/patterns.md from vision + tokens + personas."""
    return run_phase(
        phase_name="DESIGN_PATTERNS",
        config=config,
        project_dir=project_dir,
        system_prompt=design_patterns_system_prompt(project_dir),
        user_prompt=design_patterns_user_prompt(project_dir),
        validator=validate_design_patterns,
        max_attempts=max_attempts,
    )
