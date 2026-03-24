"""Shared phase runner for pre-build phases 1-5.

All agent-driven phases follow the same pattern:
1. Construct prompts
2. Invoke agent via run_local_agent + EG1
3. Validate output deterministically
4. Return PhaseResult
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from auto_sdd.lib.model_config import ModelConfig
from auto_sdd.lib.local_agent import AgentResult, run_local_agent
from auto_sdd.lib.types import GateError, PhaseResult
from auto_sdd.lib.constants import BUILD_AGENT_TOOLS
from auto_sdd.exec_gates.eg1_tool_calls import BuildAgentExecutor

logger = logging.getLogger(__name__)


# Output files per pre-build phase. Each phase's agent is only allowed
# to write its own output — all other phases' outputs are protected.
_PHASE_OUTPUTS: dict[str, list[str]] = {
    "VISION": [".specs/vision.md"],
    "SYSTEMS_DESIGN": [".specs/systems-design.md"],
    "DESIGN_SYSTEM": [".specs/design-system/tokens.md"],
    "PERSONAS": [".specs/personas.md"],
    "DESIGN_PATTERNS": [".specs/design-system/patterns.md"],
    "ROADMAP": [".specs/roadmap.md"],
    # SPEC_FIRST writes to .specs/features/**/*.md — protected per-file
    # RED writes test scaffolds — no agent, so no protection needed
}


def _protected_for_phase(phase_name: str, project_dir: Path) -> set[str]:
    """Compute protected paths for a pre-build phase.

    Returns all other phases' output files (that exist on disk) so the
    agent can't accidentally overwrite them — especially important when
    phases run in parallel.
    """
    protected: set[str] = set()
    for other_phase, outputs in _PHASE_OUTPUTS.items():
        if other_phase == phase_name:
            continue
        for rel in outputs:
            full = project_dir / rel
            if full.exists():
                protected.add(rel)
    return protected


def run_phase(
    phase_name: str,
    config: ModelConfig,
    project_dir: Path,
    system_prompt: str,
    user_prompt: str,
    validator: Callable[[Path], list[GateError]],
    max_attempts: int = 2,
) -> PhaseResult:
    """Run a single agent-driven pre-build phase.

    Pattern: invoke agent → validate output → retry or pass.
    Each phase's agent is restricted from overwriting other phases' outputs.
    """
    protected = _protected_for_phase(phase_name, project_dir)

    for attempt in range(max_attempts):
        if attempt > 0:
            logger.info("%s: retry %d/%d", phase_name, attempt, max_attempts - 1)

        executor = BuildAgentExecutor(
            project_root=project_dir,
            allowed_branch="",
            command_timeout=60,
            protected_paths=protected,
        )

        logger.info("%s: invoking agent (attempt %d)", phase_name, attempt)

        agent_result: AgentResult = run_local_agent(
            config=config,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tools=BUILD_AGENT_TOOLS,
            executor=executor,
        )

        if not agent_result.success:
            logger.warning(
                "%s: agent failed: %s", phase_name, agent_result.error,
            )
            if attempt == max_attempts - 1:
                return PhaseResult(
                    phase=phase_name,
                    passed=False,
                    errors=[GateError("AGENT_FAILED", agent_result.error)],
                )
            continue

        # Validate output
        errors = validator(project_dir)
        if errors:
            codes = [e.code for e in errors]
            logger.warning(
                "%s: validation failed: %s", phase_name, codes,
            )
            if attempt == max_attempts - 1:
                return PhaseResult(
                    phase=phase_name, passed=False, errors=errors,
                )
            # Append error context to user prompt for retry
            error_msg = "\n".join(
                f"- {e.code}: {e.detail}" for e in errors
            )
            user_prompt = (
                f"{user_prompt}\n\n"
                f"PREVIOUS ATTEMPT FAILED VALIDATION:\n{error_msg}\n"
                "Fix these issues.\n"
            )
            continue

        logger.info("%s: passed", phase_name)
        return PhaseResult(phase=phase_name, passed=True)

    # Should not reach here, but defensive
    return PhaseResult(
        phase=phase_name,
        passed=False,
        errors=[GateError("EXHAUSTED_RETRIES", f"{max_attempts} attempts")],
    )
