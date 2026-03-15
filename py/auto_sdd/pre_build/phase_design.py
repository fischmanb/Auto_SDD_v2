"""Phase 3: DESIGN SYSTEM — generate .specs/design-system/tokens.md."""
from __future__ import annotations

from pathlib import Path

from auto_sdd.lib.model_config import ModelConfig
from auto_sdd.lib.types import PhaseResult
from auto_sdd.pre_build.runner import run_phase
from auto_sdd.pre_build.prompts import (
    design_system_system_prompt,
    design_system_user_prompt,
)
from auto_sdd.pre_build.validators import validate_design_system


def run_phase_design_system(
    config: ModelConfig,
    project_dir: Path,
    max_attempts: int = 2,
) -> PhaseResult:
    """Generate .specs/design-system/tokens.md from vision."""
    return run_phase(
        phase_name="DESIGN_SYSTEM",
        config=config,
        project_dir=project_dir,
        system_prompt=design_system_system_prompt(project_dir),
        user_prompt=design_system_user_prompt(project_dir),
        validator=validate_design_system,
        max_attempts=max_attempts,
    )
