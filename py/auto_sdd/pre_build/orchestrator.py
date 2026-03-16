"""Pre-build orchestrator — runs phases 1-6 in sequence.

Each phase checks if its output already exists and is valid (resume
support). If valid, the phase is skipped. This keeps DP-1: no manual
intervention in the critical path.

Phase 6 (RED) is deterministic — no agent, no ModelConfig needed.
Phases 1-5 invoke the agent via run_local_agent + EG1.
"""
from __future__ import annotations

import logging
from pathlib import Path

from auto_sdd.lib.model_config import ModelConfig
from auto_sdd.lib.types import GateError, PhaseResult
from auto_sdd.pre_build.validators import (
    validate_vision,
    validate_systems_design,
    validate_design_system,
    validate_personas,
    validate_design_patterns,
    validate_roadmap,
    validate_all_specs,
)
from auto_sdd.pre_build.phase_vision import run_phase_vision
from auto_sdd.pre_build.phase_systems import run_phase_systems_design
from auto_sdd.pre_build.phase_design import run_phase_design_system
from auto_sdd.pre_build.phase_personas import run_phase_personas
from auto_sdd.pre_build.phase_design_patterns import run_phase_design_patterns
from auto_sdd.pre_build.phase_roadmap import run_phase_roadmap
from auto_sdd.pre_build.phase_spec import run_phase_spec_first
from auto_sdd.pre_build.phase_red import run_phase_red

logger = logging.getLogger(__name__)


def run_pre_build(
    config: ModelConfig,
    project_dir: Path,
    user_input: str = "",
    max_attempts: int = 2,
) -> list[PhaseResult]:
    """Run all pre-build phases (1-6) in sequence.

    Skips phases whose output already passes validation.
    Returns list of PhaseResult for all phases.
    Stops on first failure.
    """
    results: list[PhaseResult] = []

    # ── Phase 1: VISION ──────────────────────────────────────────────
    if not validate_vision(project_dir):
        logger.info("VISION: output already valid — skipping")
        results.append(PhaseResult(phase="VISION", passed=True))
    else:
        if not user_input:
            results.append(PhaseResult(
                phase="VISION",
                passed=False,
                errors=[GateError(
                    "VISION_NO_INPUT",
                    "Phase 1 (VISION) requires user_input but none provided",
                )],
            ))
            return results

        result = run_phase_vision(config, project_dir, user_input, max_attempts)
        results.append(result)
        if not result.passed:
            return results

    # ── Phase 2: SYSTEMS DESIGN ──────────────────────────────────────
    if not validate_systems_design(project_dir):
        logger.info("SYSTEMS_DESIGN: output already valid — skipping")
        results.append(PhaseResult(phase="SYSTEMS_DESIGN", passed=True))
    else:
        result = run_phase_systems_design(config, project_dir, max_attempts)
        results.append(result)
        if not result.passed:
            return results

    # ── Phase 3: DESIGN SYSTEM ───────────────────────────────────────
    if not validate_design_system(project_dir):
        logger.info("DESIGN_SYSTEM: output already valid — skipping")
        results.append(PhaseResult(phase="DESIGN_SYSTEM", passed=True))
    else:
        result = run_phase_design_system(config, project_dir, max_attempts)
        results.append(result)
        if not result.passed:
            return results

    # ── Phase 3b: PERSONAS ───────────────────────────────────────────
    if not validate_personas(project_dir):
        logger.info("PERSONAS: output already valid — skipping")
        results.append(PhaseResult(phase="PERSONAS", passed=True))
    else:
        result = run_phase_personas(config, project_dir, max_attempts)
        results.append(result)
        if not result.passed:
            return results

    # ── Phase 3c: DESIGN PATTERNS ────────────────────────────────────
    if not validate_design_patterns(project_dir):
        logger.info("DESIGN_PATTERNS: output already valid — skipping")
        results.append(PhaseResult(phase="DESIGN_PATTERNS", passed=True))
    else:
        result = run_phase_design_patterns(config, project_dir, max_attempts)
        results.append(result)
        if not result.passed:
            return results

    # ── Phase 4: ROADMAP ─────────────────────────────────────────────
    if not validate_roadmap(project_dir):
        logger.info("ROADMAP: output already valid — skipping")
        results.append(PhaseResult(phase="ROADMAP", passed=True))
    else:
        result = run_phase_roadmap(config, project_dir, max_attempts)
        results.append(result)
        if not result.passed:
            return results

    # ── Phase 5: SPEC-FIRST ──────────────────────────────────────────
    if not validate_all_specs(project_dir):
        logger.info("SPEC_FIRST: all specs already valid — skipping")
        results.append(PhaseResult(phase="SPEC_FIRST", passed=True))
    else:
        result = run_phase_spec_first(config, project_dir, max_attempts)
        results.append(result)
        if not result.passed:
            return results

    # ── Phase 6: RED (deterministic — no agent) ──────────────────────
    result = run_phase_red(project_dir)
    results.append(result)
    if not result.passed:
        return results

    # All phases passed
    logger.info(
        "Pre-build complete: %d phases passed",
        len(results),
    )
    return results
