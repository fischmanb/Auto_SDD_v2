"""Phase 5: SPEC-FIRST — generate .feature.md per roadmap feature."""
from __future__ import annotations

import logging
from pathlib import Path

from auto_sdd.lib.model_config import ModelConfig
from auto_sdd.lib.types import GateError, PhaseResult
from auto_sdd.pre_build.runner import run_phase
from auto_sdd.pre_build.prompts import (
    spec_first_system_prompt,
    spec_first_user_prompt,
)
from auto_sdd.pre_build.validators import (
    validate_feature_spec,
    _parse_roadmap_table,
)

logger = logging.getLogger(__name__)


def _spec_path_for_feature(
    project_dir: Path, name: str, domain: str,
) -> Path:
    """Derive the expected spec file path for a feature."""
    slug = name.lower().replace(" ", "-")
    return project_dir / ".specs" / "features" / domain / f"{slug}.feature.md"


def run_phase_spec_first(
    config: ModelConfig,
    project_dir: Path,
    max_attempts: int = 2,
) -> PhaseResult:
    """Generate .feature.md for each pending roadmap feature.

    Reads the roadmap, iterates pending features, generates a spec
    for each one that doesn't already have a valid spec file.
    """
    roadmap_path = project_dir / ".specs" / "roadmap.md"
    if not roadmap_path.exists():
        return PhaseResult(
            phase="SPEC_FIRST",
            passed=False,
            errors=[GateError("ROADMAP_MISSING", "Cannot run SPEC_FIRST without roadmap")],
        )

    text = roadmap_path.read_text()
    features, parse_errors = _parse_roadmap_table(text)
    if parse_errors:
        return PhaseResult(
            phase="SPEC_FIRST", passed=False, errors=parse_errors,
        )

    # Filter to pending features (⬜)
    pending = {
        name: data for name, data in features.items()
        if "⬜" in data["status"]
    }

    if not pending:
        logger.info("SPEC_FIRST: no pending features — skipping")
        return PhaseResult(phase="SPEC_FIRST", passed=True)

    all_errors: list[GateError] = []

    for name, data in pending.items():
        domain = data.get("domain", "general")

        spec_path = _spec_path_for_feature(project_dir, name, domain)

        # Skip if spec already exists and is valid
        if spec_path.exists():
            existing_errors = validate_feature_spec(spec_path)
            if not existing_errors:
                logger.info("SPEC_FIRST: %s already has valid spec — skipping", name)
                continue

        complexity = data.get("complexity", "M")
        deps = data["deps"]

        def _validator(pd: Path, sp=spec_path) -> list[GateError]:
            return validate_feature_spec(sp)

        result = run_phase(
            phase_name=f"SPEC_FIRST:{name}",
            config=config,
            project_dir=project_dir,
            system_prompt=spec_first_system_prompt(project_dir),
            user_prompt=spec_first_user_prompt(
                project_dir, name, domain, deps, complexity,
            ),
            validator=_validator,
            max_attempts=max_attempts,
        )

        if not result.passed:
            all_errors.extend(result.errors)
            logger.warning("SPEC_FIRST: failed for %s", name)

    if all_errors:
        return PhaseResult(
            phase="SPEC_FIRST", passed=False, errors=all_errors,
        )

    return PhaseResult(phase="SPEC_FIRST", passed=True)
