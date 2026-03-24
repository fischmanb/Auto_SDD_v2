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
    # Dispatch: Anthropic API vs OpenAI-compatible
    if "anthropic.com" in (config.base_url or ""):
        return _run_anthropic_agent(
            config=config,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tools=tools,
            executor=executor,
        )

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
    # After _MAX_NUDGES without any write, hard-stop the agent.
    _READ_ONLY_NUDGE_THRESHOLD = 12
    _MAX_NUDGES = 2
    turns_since_write = 0
    nudge_count = 0
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
        has_text = bool(assistant_msg.content and assistant_msg.content.strip())
        has_tools = bool(assistant_msg.tool_calls)
        logger.info(
            "Turn %d: finish_reason=%s, has_text=%s, has_tools=%s",
            turn, choice.finish_reason, has_text, has_tools,
        )

        if choice.finish_reason == "stop":
            result.output = assistant_msg.content or ""
            result.finish_reason = "stop"
            logger.info(
                "Agent completed in %d turns (%.1fs). Output length: %d chars",
                result.turn_count,
                time.monotonic() - start_time,
                len(result.output),
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

            # Nudge: if stuck reading without writing, inject a redirect.
            # After _MAX_NUDGES without any write, hard-stop — the agent
            # is stuck in an exploration loop and burning turns.
            if turns_since_write >= _READ_ONLY_NUDGE_THRESHOLD and not has_written:
                nudge_count += 1
                if nudge_count > _MAX_NUDGES:
                    result.finish_reason = "error"
                    result.error = (
                        f"Agent stuck: {nudge_count} nudges given over "
                        f"{turn + 1} turns with no writes. Hard-stopping."
                    )
                    result.output = assistant_msg.content or ""
                    logger.warning(
                        "Hard-stop: agent stuck after %d nudges, %d turns, 0 writes",
                        nudge_count, turn + 1,
                    )
                    break
                nudge = (
                    "You have spent several turns reading files without writing any code. "
                    "You have enough context. Start implementing NOW by using write_file "
                    "to create the source files for this feature. Do not read any more files."
                )
                messages.append({"role": "user", "content": nudge})
                logger.info(
                    "Nudge %d/%d injected at turn %d (no writes in %d turns)",
                    nudge_count, _MAX_NUDGES, turn, turns_since_write,
                )
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

        # ── Context management: trim old tool results ────────────────
        # Tool results (file contents, ls output) bloat context fast.
        # Keep last 2 tool results full, truncate older ones to summary.
        # This is where context management actually happens — individual
        # reads return full content so the model doesn't re-read.
        _trim_old_tool_results(messages, keep_recent=2)

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

        # Log every tool call at INFO so we can see the model's behavior
        arg_summary = ""
        if fn_name == "read_file":
            arg_summary = fn_args.get("path", fn_args.get("command", "?"))
        elif fn_name == "write_file":
            arg_summary = fn_args.get("path", "?")
        elif fn_name == "run_command":
            arg_summary = fn_args.get("command", "?")[:60]
        else:
            arg_summary = str(list(fn_args.keys()))[:60]
        logger.info("Turn %d: %s(%s)", turn, fn_name, arg_summary)

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


def _trim_old_tool_results(
    messages: list[dict[str, Any]], keep_recent: int = 4,
) -> None:
    """Truncate old tool result messages to prevent context bloat.

    Tool results (file contents, directory listings, command output) fill
    the context window fast. After keep_recent full results, older ones
    are truncated to a brief summary.

    This is the input-side complement to max_tokens (output-side).
    Without it, 8 reads × 8KB = 64KB of tool results leaves no room
    for the model to generate code.
    """
    tool_indices = [
        i for i, m in enumerate(messages) if m.get("role") == "tool"
    ]

    if len(tool_indices) <= keep_recent:
        return

    # Truncate all but the most recent keep_recent tool results
    for idx in tool_indices[:-keep_recent]:
        content = messages[idx].get("content", "")
        if len(content) > 200:
            # Try to parse as JSON and keep just the metadata
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    # Keep path/status/error, drop content
                    summary = {}
                    for key in ("path", "status", "error", "returncode",
                                "size", "truncated", "bytes_written"):
                        if key in parsed:
                            summary[key] = parsed[key]
                    if "content" in parsed:
                        summary["content"] = "(trimmed — see original file)"
                    if "stdout" in parsed:
                        summary["stdout"] = parsed["stdout"][:100] + "..." if len(parsed.get("stdout", "")) > 100 else parsed.get("stdout", "")
                    messages[idx]["content"] = json.dumps(summary)
                else:
                    messages[idx]["content"] = content[:200] + "...(trimmed)"
            except (json.JSONDecodeError, TypeError):
                messages[idx]["content"] = content[:200] + "...(trimmed)"


# ── Anthropic API agent ──────────────────────────────────────────────────────


def _convert_tools_openai_to_anthropic(
    tools: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Convert OpenAI tool format to Anthropic tool format."""
    if not tools:
        return None
    anthropic_tools = []
    for tool in tools:
        fn = tool.get("function", {})
        anthropic_tools.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return anthropic_tools


def _run_anthropic_agent(
    config: ModelConfig,
    system_prompt: str,
    user_prompt: str,
    tools: list[dict[str, Any]] | None,
    executor: ToolExecutor,
) -> AgentResult:
    """Run agent loop against Anthropic Messages API.

    Same logic as the OpenAI path: multi-turn tool calling with
    nudge, trimming, and EG1 enforcement. Different wire format.
    """
    import anthropic

    client = anthropic.Anthropic(
        api_key=config.api_key,
        timeout=config.timeout_seconds,
    )

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_prompt},
    ]
    anthropic_tools = _convert_tools_openai_to_anthropic(tools) or []

    result = AgentResult()
    start_time = time.monotonic()

    _READ_ONLY_NUDGE_THRESHOLD = 12
    _MAX_NUDGES = 2
    turns_since_write = 0
    nudge_count = 0
    has_written = False

    for turn in range(config.max_turns):
        result.turn_count = turn + 1

        try:
            kwargs: dict[str, Any] = {
                "model": config.model,
                "system": system_prompt,
                "messages": messages,
                "max_tokens": config.max_tokens,
                "temperature": config.temperature,
            }
            if anthropic_tools:
                kwargs["tools"] = anthropic_tools
                kwargs["tool_choice"] = {"type": "auto"}
            response = client.messages.create(**kwargs)
        except Exception as exc:
            result.finish_reason = "error"
            result.error = f"Anthropic API call failed on turn {turn}: {exc}"
            logger.error("Anthropic request failed on turn %d: %s", turn, exc)
            break

        # Parse response content blocks
        text_parts = []
        tool_uses = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        has_text = bool(text_parts)
        has_tools = bool(tool_uses)
        logger.info(
            "Turn %d: stop_reason=%s, has_text=%s, has_tools=%s",
            turn, response.stop_reason, has_text, has_tools,
        )

        # Build assistant message for history (full content blocks)
        assistant_content = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
        messages.append({"role": "assistant", "content": assistant_content})

        # Route on stop_reason
        if response.stop_reason == "end_turn":
            result.output = "\n".join(text_parts)
            result.finish_reason = "stop"
            result.finish_reason = "stop"
            logger.info(
                "Agent completed in %d turns (%.1fs). Output length: %d chars",
                result.turn_count,
                time.monotonic() - start_time,
                len(result.output),
            )
            break

        elif response.stop_reason == "tool_use" and tool_uses:
            tool_results = []
            for tu in tool_uses:
                fn_name = tu.name
                fn_args = tu.input if isinstance(tu.input, dict) else {}

                arg_summary = ""
                if fn_name == "read_file":
                    arg_summary = fn_args.get("path", "?")
                elif fn_name == "write_file":
                    arg_summary = fn_args.get("path", "?")
                elif fn_name == "run_command":
                    arg_summary = fn_args.get("command", "?")[:60]
                logger.info("Turn %d: %s(%s)", turn, fn_name, arg_summary)

                record = ToolCallRecord(
                    turn=turn, name=fn_name, arguments=fn_args, result="",
                )
                tool_result = _execute_with_gate(executor, fn_name, fn_args, record)
                result.tool_calls.append(record)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": tool_result,
                })

            # Feed results back as user message
            messages.append({"role": "user", "content": tool_results})

            # Track writes for nudge
            wrote_this_turn = any(tu.name == "write_file" for tu in tool_uses)
            if wrote_this_turn:
                turns_since_write = 0
                has_written = True
            else:
                turns_since_write += 1

            if turns_since_write >= _READ_ONLY_NUDGE_THRESHOLD and not has_written:
                nudge_count += 1
                if nudge_count > _MAX_NUDGES:
                    result.finish_reason = "error"
                    result.error = (
                        f"Agent stuck: {nudge_count} nudges given over "
                        f"{turn + 1} turns with no writes. Hard-stopping."
                    )
                    result.output = "\n".join(text_parts)
                    logger.warning(
                        "Hard-stop: agent stuck after %d nudges, %d turns, 0 writes",
                        nudge_count, turn + 1,
                    )
                    break
                nudge = (
                    "You have spent several turns reading files without writing any code. "
                    "You have enough context. Start implementing NOW by using write_file "
                    "to create the source files for this feature. Do not read any more files."
                )
                messages.append({"role": "user", "content": nudge})
                logger.info(
                    "Nudge %d/%d injected at turn %d (no writes in %d turns)",
                    nudge_count, _MAX_NUDGES, turn, turns_since_write,
                )
                turns_since_write = 0

        elif response.stop_reason == "max_tokens":
            result.finish_reason = "length"
            result.error = "max_tokens exhausted"
            result.output = "\n".join(text_parts)
            logger.warning("max_tokens exceeded on turn %d", turn)
            break

        else:
            logger.warning(
                "Unexpected stop_reason=%r on turn %d", response.stop_reason, turn,
            )

        # Trim old tool results for context management
        _trim_old_anthropic_results(messages, keep_recent=2)

    else:
        result.finish_reason = "max_turns"
        result.error = f"Reached {config.max_turns} turns without completion"
        logger.warning("Agent hit max_turns (%d)", config.max_turns)

    result.duration_seconds = time.monotonic() - start_time
    return result


def _trim_old_anthropic_results(
    messages: list[dict[str, Any]], keep_recent: int = 2,
) -> None:
    """Trim old tool_result content in Anthropic message format.

    Anthropic tool results are user messages with content blocks
    of type "tool_result". Trim content in older results to prevent
    context bloat, same as the OpenAI path.
    """
    # Find user messages that contain tool_result blocks
    result_indices = []
    for i, msg in enumerate(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        ):
            result_indices.append(i)

    if len(result_indices) <= keep_recent:
        return

    for idx in result_indices[:-keep_recent]:
        content = messages[idx].get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            original = block.get("content", "")
            if isinstance(original, str) and len(original) > 200:
                try:
                    parsed = json.loads(original)
                    if isinstance(parsed, dict):
                        summary = {}
                        for key in ("path", "status", "error", "returncode",
                                    "size", "truncated", "bytes_written"):
                            if key in parsed:
                                summary[key] = parsed[key]
                        if "content" in parsed:
                            summary["content"] = "(trimmed)"
                        if "stdout" in parsed:
                            summary["stdout"] = parsed["stdout"][:100] + "..."
                        block["content"] = json.dumps(summary)
                    else:
                        block["content"] = original[:200] + "...(trimmed)"
                except (json.JSONDecodeError, TypeError):
                    block["content"] = original[:200] + "...(trimmed)"
