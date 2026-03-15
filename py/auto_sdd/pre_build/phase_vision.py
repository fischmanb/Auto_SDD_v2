"""Phase 1: VISION — generate .specs/vision.md."""
from __future__ import annotations

from pathlib import Path

from auto_sdd.lib.model_config import ModelConfig
from auto_sdd.lib.types import PhaseResult
from auto_sdd.pre_build.runner import run_phase
from auto_sdd.pre_build.prompts import vision_system_prompt, vision_user_prompt
from auto_sdd.pre_build.validators import validate_vision


def run_phase_vision(
    config: ModelConfig,
    project_dir: Path,
    user_input: str,
    max_attempts: int = 2,
) -> PhaseResult:
    """Generate .specs/vision.md from user input."""
    return run_phase(
        phase_name="VISION",
        config=config,
        project_dir=project_dir,
        system_prompt=vision_system_prompt(project_dir),
        user_prompt=vision_user_prompt(project_dir, user_input),
        validator=validate_vision,
        max_attempts=max_attempts,
    )
