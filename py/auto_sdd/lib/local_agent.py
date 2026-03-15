"""OpenAI-compatible client wrapper for local LLM agents.

Implements a multi-turn tool-calling completion loop against any server
exposing the OpenAI Chat Completions API (LM Studio, Ollama, llama.cpp,
vLLM). Designed around GPT-OSS Harmony behavior but works with any
OpenAI-compatible model.

The tool execution boundary is the ExecGate (EG1) intercept point:
the agent proposes tool calls, the ToolExecutor decides whether to
run them. The loop never executes tools directly.

Dependencies: openai
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from openai import OpenAI

from auto_sdd.lib.model_config import ModelConfig

logger = logging.getLogger(__name__)


# ── Tool execution protocol ──────────────────────────────────────────────────


class ToolCallBlocked(Exception):
    """Raised by a ToolExecutor to reject a tool call.

    The rejection reason is fed back to the model as an error result,
    giving it a chance to try a different approach.
    """


class ToolExecutor(Protocol):
    """Protocol for tool execution — the EG1 intercept boundary.

    Implementations validate the proposed tool call against whatever
    rules the ExecGate enforces (path restrictions, command allowlists,
    scope boundaries), then either execute and return a JSON result
    string, or raise ToolCallBlocked to reject.
    """

    def execute(self, name: str, arguments: dict[str, Any]) -> str: ...


# ── Result types ─────────────────────────────────────────────────────────────


@dataclass
class ToolCallRecord:
    """Record of a single tool call within an agent run."""

    turn: int
    name: str
    arguments: dict[str, Any]
    result: str
    blocked: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "name": self.name,
            "arguments": self.arguments,
            "result": self.result[:500],  # Truncate for logging
            "blocked": self.blocked,
            "error": self.error,
        }


@dataclass
class AgentResult:
    """Structured result from a local agent run."""

    output: str = ""
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    turn_count: int = 0
    finish_reason: str = ""  # stop | length | max_turns | error
    error: str = ""
    duration_seconds: float = 0.0

    @property
    def success(self) -> bool:
        return self.finish_reason == "stop" and not self.error

    def to_dict(self) -> dict[str, Any]:
        return {
            "output": self.output[:2000],  # Truncate for logging
            "tool_call_count": len(self.tool_calls),
            "turn_count": self.turn_count,
            "finish_reason": self.finish_reason,
            "error": self.error,
            "duration_seconds": round(self.duration_seconds, 2),
            "success": self.success,
        }


# ── Core completion loop ─────────────────────────────────────────────────────


def run_local_agent(
    config: ModelConfig,
    system_prompt: str,
    user_prompt: str,
    tools: list[dict[str, Any]] | None,
    executor: ToolExecutor,
) -> AgentResult:
    """Run a multi-turn tool-calling agent loop against a local LLM.

    This is the core completion loop for Simplified Build Loop V2.
    It replaces claude_wrapper.py's run_claude() with a direct HTTP
    API integration against the local model server.

    Flow per turn:
        1. Send messages + tool definitions to model
        2. If finish_reason="stop" → return final output
        3. If finish_reason="tool_calls" → extract call, pass to executor
           (this is the EG1 boundary — executor validates before running)
        4. Feed tool result back, strip old reasoning, continue loop
        5. If finish_reason="length" → error, budget exhausted
        6. After max_turns → error, loop didn't terminate

    Args:
        config: Model serving configuration.
        system_prompt: Instructions for the agent (uses "developer" or
                       "system" role per config.use_developer_role).
        user_prompt: The task for the agent to accomplish.
        tools: OpenAI-format tool definitions, or None for no tools.
        executor: ToolExecutor implementation (EG1 intercept point).

    Returns:
        AgentResult with final output, tool call records, and metadata.
    """
    client = OpenAI(
        base_url=config.base_url,
        api_key=config.api_key,
        timeout=config.timeout_seconds,
    )

    messages: list[dict[str, Any]] = [
        {"role": config.system_role, "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = AgentResult()
    start_time = time.monotonic()

    # Track consecutive turns without write_file to detect exploration loops.
    # After _READ_ONLY_NUDGE_THRESHOLD turns of reads with no writes,
    # inject a user message forcing the model to start implementing.
    _READ_ONLY_NUDGE_THRESHOLD = 8
    turns_since_write = 0
    has_written = False

    for turn in range(config.max_turns):
        result.turn_count = turn + 1

        # ── Build completion kwargs ──────────────────────────────────
        completion_kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "top_p": config.top_p,
        }

        # Only include tools/tool_choice if we have tool definitions
        if tools:
            completion_kwargs["tools"] = tools
            completion_kwargs["tool_choice"] = "auto"

        # Pass any extra params from config (e.g., reasoning_effort
        # if the server supports it as a parameter)
        completion_kwargs.update(config.extra_params)

        # ── Make the API call ────────────────────────────────────────
        try:
            response = client.chat.completions.create(**completion_kwargs)
        except Exception as exc:
            result.finish_reason = "error"
            result.error = f"API call failed on turn {turn}: {exc}"
            logger.error("Completion request failed on turn %d: %s", turn, exc)
            break

        choice = response.choices[0]
        assistant_msg = choice.message

        # ── Append assistant message to history ──────────────────────
        msg_dict = _build_assistant_history_entry(assistant_msg)
        messages.append(msg_dict)

        # ── Route on finish_reason ───────────────────────────────────

        if choice.finish_reason == "stop":
            result.output = assistant_msg.content or ""
            result.finish_reason = "stop"
            logger.info(
                "Agent completed in %d turns (%.1fs)",
                result.turn_count,
                time.monotonic() - start_time,
            )
            break

        elif choice.finish_reason == "tool_calls" and assistant_msg.tool_calls:
            _handle_tool_calls(
                turn=turn,
                tool_calls=assistant_msg.tool_calls,
                executor=executor,
                messages=messages,
                result=result,
            )

            # Track write_file calls to detect exploration loops
            wrote_this_turn = any(
                tc.function.name == "write_file"
                for tc in assistant_msg.tool_calls
            )
            if wrote_this_turn:
                turns_since_write = 0
                has_written = True
            else:
                turns_since_write += 1

            # Nudge: if stuck reading without writing, inject a redirect
            if turns_since_write >= _READ_ONLY_NUDGE_THRESHOLD and not has_written:
                nudge = (
                    "You have spent several turns reading files without writing any code. "
                    "You have enough context. Start implementing NOW by using write_file "
                    "to create the source files for this feature. Do not read any more files."
                )
                messages.append({"role": "user", "content": nudge})
                logger.info("Nudge injected at turn %d (no writes in %d turns)", turn, turns_since_write)
                turns_since_write = 0  # reset so we don't spam

        elif choice.finish_reason == "length":
            result.finish_reason = "length"
            result.error = (
                "max_tokens exhausted — model ran out of output budget. "
                "Reasoning tokens may have consumed the allocation."
            )
            result.output = assistant_msg.content or ""
            logger.warning("max_tokens exceeded on turn %d", turn)
            break

        else:
            logger.warning(
                "Unexpected finish_reason=%r on turn %d — continuing",
                choice.finish_reason,
                turn,
            )

        # ── Context management: strip old reasoning ──────────────────
        if config.strip_reasoning_older_turns:
            _strip_older_reasoning(messages)

    else:
        # for/else: exhausted max_turns without break
        result.finish_reason = "max_turns"
        result.error = f"Reached {config.max_turns} turns without completion"
        logger.warning("Agent hit max_turns (%d)", config.max_turns)

    result.duration_seconds = time.monotonic() - start_time
    return result


# ── Internal helpers ─────────────────────────────────────────────────────────


def _build_assistant_history_entry(
    assistant_msg: Any,
) -> dict[str, Any]:
    """Convert an assistant message to a history dict.

    Preserves reasoning_content (GPT-OSS analysis channel) and
    tool_calls for proper multi-turn context.
    """
    msg_dict: dict[str, Any] = {
        "role": "assistant",
        "content": assistant_msg.content,
    }

    # Preserve reasoning_content if present (GPT-OSS Harmony format)
    reasoning = getattr(assistant_msg, "reasoning_content", None)
    if reasoning is not None:
        msg_dict["reasoning_content"] = reasoning

    # Preserve tool calls in history
    if assistant_msg.tool_calls:
        msg_dict["tool_calls"] = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in assistant_msg.tool_calls
        ]

    return msg_dict


def _handle_tool_calls(
    turn: int,
    tool_calls: list[Any],
    executor: ToolExecutor,
    messages: list[dict[str, Any]],
    result: AgentResult,
) -> None:
    """Process tool calls from a single assistant turn.

    GPT-OSS should emit one tool call per turn (parallel calling is
    broken), but we handle multiple defensively — processing each
    sequentially through the executor.
    """
    if len(tool_calls) > 1:
        logger.warning(
            "Model emitted %d tool calls in one turn — processing "
            "sequentially (parallel calling is unreliable)",
            len(tool_calls),
        )

    for tool_call in tool_calls:
        fn_name = tool_call.function.name
        fn_args = _parse_tool_arguments(fn_name, tool_call.function.arguments)

        record = ToolCallRecord(
            turn=turn,
            name=fn_name,
            arguments=fn_args,
            result="",
        )

        # ── EG1 intercept: executor validates and runs ───────────
        tool_result = _execute_with_gate(executor, fn_name, fn_args, record)

        result.tool_calls.append(record)

        # Feed result back to model
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": tool_result,
        })


def _parse_tool_arguments(fn_name: str, raw_arguments: str) -> dict[str, Any]:
    """Defensively parse tool call arguments from JSON string.

    GPT-OSS structured output is not guaranteed locally — the model
    may emit malformed JSON. We parse what we can and preserve the
    raw string on failure.
    """
    try:
        args = json.loads(raw_arguments)
        if not isinstance(args, dict):
            logger.warning(
                "Tool %s arguments parsed to %s, expected dict — wrapping",
                fn_name,
                type(args).__name__,
            )
            return {"_parsed": args, "_raw": raw_arguments}
        return args
    except json.JSONDecodeError as exc:
        logger.warning(
            "Invalid JSON in tool call arguments for %s: %s",
            fn_name,
            exc,
        )
        return {"_raw": raw_arguments, "_parse_error": str(exc)}


def _execute_with_gate(
    executor: ToolExecutor,
    fn_name: str,
    fn_args: dict[str, Any],
    record: ToolCallRecord,
) -> str:
    """Run a tool call through the executor (EG1 gate).

    Returns the result string to feed back to the model.
    On block or error, returns a structured error JSON that gives
    the model a chance to adjust its approach.
    """
    try:
        tool_result = executor.execute(fn_name, fn_args)
        record.result = tool_result
        logger.debug("Tool %s executed successfully", fn_name)
        return tool_result

    except ToolCallBlocked as exc:
        record.blocked = True
        record.error = str(exc)
        logger.info(
            "EG1 blocked: %s(%s) — %s",
            fn_name,
            _truncate_args(fn_args),
            exc,
        )
        return json.dumps({
            "error": f"Tool call blocked by execution gate: {exc}",
            "blocked": True,
        })

    except Exception as exc:
        record.error = str(exc)
        logger.error(
            "Tool execution failed: %s(%s) — %s",
            fn_name,
            _truncate_args(fn_args),
            exc,
        )
        return json.dumps({
            "error": f"Tool execution failed: {exc}",
        })


def _strip_older_reasoning(messages: list[dict[str, Any]]) -> None:
    """Remove reasoning_content from all but the last assistant message.

    Per GPT-OSS model card: "In multi-turn conversations the reasoning
    traces from past assistant turns should be removed." This prevents
    context bloat and quality degradation in long tool-calling sessions.
    """
    assistant_indices = [
        i for i, m in enumerate(messages) if m.get("role") == "assistant"
    ]

    # Keep reasoning only on the most recent assistant turn
    if len(assistant_indices) > 1:
        for idx in assistant_indices[:-1]:
            messages[idx].pop("reasoning_content", None)


def _truncate_args(args: dict[str, Any], max_len: int = 120) -> str:
    """Truncate arguments dict for log output."""
    s = json.dumps(args)
    return s[:max_len] + "..." if len(s) > max_len else s
