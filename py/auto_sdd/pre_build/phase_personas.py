"""Phase 3b: PERSONAS — generate .specs/personas.md.

Runs after design tokens (phase 3). Produces user personas informed
by the vision and the established visual vocabulary. Personas feed
into the design patterns phase (3c) and spec generation (phase 5).
"""
from __future__ import annotations

from pathlib import Path

from auto_sdd.lib.model_config import ModelConfig
from auto_sdd.lib.types import PhaseResult
from auto_sdd.pre_build.runner import run_phase
from auto_sdd.pre_build.prompts import (
    personas_system_prompt,
    personas_user_prompt,
)
from auto_sdd.pre_build.validators import validate_personas


def run_phase_personas(
    config: ModelConfig,
    project_dir: Path,
    max_attempts: int = 2,
) -> PhaseResult:
    """Generate .specs/personas.md from vision + tokens."""
    return run_phase(
        phase_name="PERSONAS",
        config=config,
        project_dir=project_dir,
        system_prompt=personas_system_prompt(project_dir),
        user_prompt=personas_user_prompt(project_dir),
        validator=validate_personas,
        max_attempts=max_attempts,
    )
