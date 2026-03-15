"""Phase 2: SYSTEMS DESIGN — generate .specs/systems-design.md."""
from __future__ import annotations

from pathlib import Path

from auto_sdd.lib.model_config import ModelConfig
from auto_sdd.lib.types import PhaseResult
from auto_sdd.pre_build.runner import run_phase
from auto_sdd.pre_build.prompts import (
    systems_design_system_prompt,
    systems_design_user_prompt,
)
from auto_sdd.pre_build.validators import validate_systems_design


def run_phase_systems_design(
    config: ModelConfig,
    project_dir: Path,
    max_attempts: int = 2,
) -> PhaseResult:
    """Generate .specs/systems-design.md from vision."""
    return run_phase(
        phase_name="SYSTEMS_DESIGN",
        config=config,
        project_dir=project_dir,
        system_prompt=systems_design_system_prompt(project_dir),
        user_prompt=systems_design_user_prompt(project_dir),
        validator=validate_systems_design,
        max_attempts=max_attempts,
    )
