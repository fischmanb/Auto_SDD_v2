"""Pre-build orchestrator — runs phases 1-6.

Each phase checks if its output already exists and is valid (resume
support). If valid, the phase is skipped. This keeps DP-1: no manual
intervention in the critical path.

Phase 6 (RED) is deterministic — no agent, no ModelConfig needed.
Phases 1-5 invoke the agent via run_local_agent + EG1.

Phases 3 (Design System) and 3b (Personas) run in parallel — they
both depend only on Vision + Systems Design. Phase 3c (Design Patterns)
runs after both complete because it reads their outputs.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, Future
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
    """Run all pre-build phases (1-6).

    Phases 3 and 3b run in parallel (both depend only on phases 1-2).
    Phase 3c waits for both before running (reads their outputs).
    All other phases run sequentially. Stops on first failure.
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

    # ── Phases 3 + 3b: DESIGN SYSTEM & PERSONAS (parallel) ──────────
    # Both depend only on Vision + Systems Design outputs.
    # Running them concurrently saves one full agent call of wall-clock time.
    design_needs_run = validate_design_system(project_dir)
    personas_needs_run = validate_personas(project_dir)

    if not design_needs_run and not personas_needs_run:
        # Both already valid
        logger.info("DESIGN_SYSTEM: output already valid — skipping")
        logger.info("PERSONAS: output already valid — skipping")
        results.append(PhaseResult(phase="DESIGN_SYSTEM", passed=True))
        results.append(PhaseResult(phase="PERSONAS", passed=True))
    elif design_needs_run and personas_needs_run:
        # Both need running — do them in parallel
        logger.info("Running DESIGN_SYSTEM and PERSONAS in parallel")
        with ThreadPoolExecutor(max_workers=2) as pool:
            design_future: Future[PhaseResult] = pool.submit(
                run_phase_design_system, config, project_dir, max_attempts,
            )
            personas_future: Future[PhaseResult] = pool.submit(
                run_phase_personas, config, project_dir, max_attempts,
            )
            design_result = design_future.result()
            personas_result = personas_future.result()

        results.append(design_result)
        results.append(personas_result)

        # If either failed, stop
        if not design_result.passed:
            return results
        if not personas_result.passed:
            return results
    else:
        # One valid, one needs running — run the needed one only
        if design_needs_run:
            result = run_phase_design_system(config, project_dir, max_attempts)
            results.append(result)
            if not result.passed:
                return results
            results.append(PhaseResult(phase="PERSONAS", passed=True))
        else:
            results.append(PhaseResult(phase="DESIGN_SYSTEM", passed=True))
            result = run_phase_personas(config, project_dir, max_attempts)
            results.append(result)
            if not result.passed:
                return results

    # ── Phase 3c: DESIGN PATTERNS ────────────────────────────────────
    # Depends on both tokens.md (phase 3) and personas.md (phase 3b).
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
