"""Phase 4: ROADMAP — generate .specs/roadmap.md."""
from __future__ import annotations

from pathlib import Path

from auto_sdd.lib.model_config import ModelConfig
from auto_sdd.lib.types import PhaseResult
from auto_sdd.pre_build.runner import run_phase
from auto_sdd.pre_build.prompts import roadmap_system_prompt, roadmap_user_prompt
from auto_sdd.pre_build.validators import validate_roadmap


def run_phase_roadmap(
    config: ModelConfig,
    project_dir: Path,
    max_attempts: int = 2,
) -> PhaseResult:
    """Generate .specs/roadmap.md from vision."""
    return run_phase(
        phase_name="ROADMAP",
        config=config,
        project_dir=project_dir,
        system_prompt=roadmap_system_prompt(project_dir),
        user_prompt=roadmap_user_prompt(project_dir),
        validator=validate_roadmap,
        max_attempts=max_attempts,
    )
