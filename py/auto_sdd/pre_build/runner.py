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
from typing import Any, Callable

from auto_sdd.lib.model_config import ModelConfig
from auto_sdd.lib.local_agent import AgentResult, run_local_agent
from auto_sdd.lib.types import GateError, PhaseResult
from auto_sdd.exec_gates.eg1_tool_calls import BuildAgentExecutor

logger = logging.getLogger(__name__)

# Same tool definitions as the build loop
BUILD_AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file, creating dirs as needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to project root"},
                    "content": {"type": "string", "description": "Complete file content"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to project root"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command and return stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    },
]


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
    """
    for attempt in range(max_attempts):
        if attempt > 0:
            logger.info("%s: retry %d/%d", phase_name, attempt, max_attempts - 1)

        executor = BuildAgentExecutor(
            project_root=project_dir,
            allowed_branch="",
            command_timeout=60,
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
