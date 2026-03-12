#!/usr/bin/env python3
"""Tool-call validation script for local LLM serving.

Standalone test that validates tool calling works correctly between
the local model server (LM Studio / Ollama / llama.cpp) and our
agent client before wiring anything into the build loop.

Tests:
  1. Basic connectivity — can we reach the server?
  2. Simple completion — does the model respond without tools?
  3. Tool-call round trip — does the model emit a tool call, and can
     we feed the result back and get a final response?
  4. Multi-turn tool calls — can the model chain 2+ tool calls?
  5. Reasoning content — does the model emit reasoning_content,
     and does stripping work?
  6. Blocked tool call — does the model recover when a tool is rejected?

Usage:
  # With default config (gpt-oss-120b.yaml)
  cd Auto_SDD_v2
  .venv/bin/python scripts/validate_tool_calling.py

  # With specific config
  .venv/bin/python scripts/validate_tool_calling.py config/models/gpt-oss-20b.yaml
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

# ── Add project root to path so we can import our modules ────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "py"))

from auto_sdd.lib.model_config import ModelConfig  # noqa: E402

# ── ANSI colors ──────────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"

# ── Test tool definitions ────────────────────────────────────────────────────

TEST_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to read",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write",
                    },
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
]


# ── Helpers ──────────────────────────────────────────────────────────────────

passed = 0
failed = 0
skipped = 0


def result(name: str, ok: bool, detail: str = "", warn: str = "") -> None:
    """Print a test result and update counters."""
    global passed, failed
    if ok:
        passed += 1
        print(f"  {GREEN}✓{RESET} {name}")
    else:
        failed += 1
        print(f"  {RED}✗{RESET} {name}")
    if detail:
        print(f"    {DIM}{detail}{RESET}")
    if warn:
        print(f"    {YELLOW}⚠ {warn}{RESET}")


def skip(name: str, reason: str) -> None:
    """Print a skipped test."""
    global skipped
    skipped += 1
    print(f"  {YELLOW}○{RESET} {name} {DIM}(skipped: {reason}){RESET}")


def section(title: str) -> None:
    """Print a section header."""
    print(f"\n{BOLD}{CYAN}── {title} ──{RESET}")


def timed_call(fn, *args, **kwargs):
    """Call fn and return (result, elapsed_seconds)."""
    t0 = time.monotonic()
    res = fn(*args, **kwargs)
    return res, time.monotonic() - t0


# ── Test implementations ─────────────────────────────────────────────────────


def test_connectivity(client: OpenAI, config: ModelConfig) -> bool:
    """Test 1: Can we reach the server and list models?"""
    section("Test 1: Connectivity")
    try:
        models = client.models.list()
        model_ids = [m.id for m in models.data]
        result(
            "Server reachable",
            True,
            f"Found {len(model_ids)} model(s): {', '.join(model_ids[:3])}",
        )
        # Check if our configured model is available
        if model_ids:
            found = config.model in model_ids
            result(
                f"Model '{config.model}' available",
                found,
                warn="" if found else (
                    f"Model not found. Available: {', '.join(model_ids)}. "
                    "Completion may still work if LM Studio auto-selects."
                ),
            )
        return True
    except Exception as exc:
        result("Server reachable", False, str(exc))
        return False


def test_simple_completion(client: OpenAI, config: ModelConfig) -> bool:
    """Test 2: Does the model respond to a basic prompt (no tools)?"""
    section("Test 2: Simple completion (no tools)")
    try:
        resp, elapsed = timed_call(
            client.chat.completions.create,
            model=config.model,
            messages=[
                {"role": config.system_role, "content": "You are a helpful assistant. Respond briefly."},
                {"role": "user", "content": "Say 'hello world' and nothing else."},
            ],
            max_tokens=100,
            temperature=0.0,
        )
        choice = resp.choices[0]
        content = choice.message.content or ""
        result(
            "Got response",
            bool(content.strip()),
            f"finish_reason={choice.finish_reason}, "
            f"content={content.strip()[:80]!r}, "
            f"elapsed={elapsed:.1f}s",
        )
        # Check for reasoning_content (GPT-OSS Harmony feature)
        reasoning = getattr(choice.message, "reasoning_content", None)
        if reasoning:
            result(
                "Reasoning content present",
                True,
                f"reasoning_content={reasoning[:80]!r}...",
            )
        else:
            result(
                "Reasoning content present",
                False,
                warn="No reasoning_content — model may not use Harmony format, "
                "or the server strips it. Non-fatal.",
            )
        return True
    except Exception as exc:
        result("Got response", False, str(exc))
        return False


def test_tool_call_roundtrip(client: OpenAI, config: ModelConfig) -> bool:
    """Test 3: Does the model emit a tool call and accept a result?"""
    section("Test 3: Tool-call round trip")
    try:
        # Step 1: Ask something that requires reading a file
        resp, elapsed = timed_call(
            client.chat.completions.create,
            model=config.model,
            messages=[
                {
                    "role": config.system_role,
                    "content": (
                        "You are a build agent. Use the provided tools to "
                        "accomplish tasks. Call tools one at a time."
                    ),
                },
                {
                    "role": "user",
                    "content": "Read the file at path 'package.json' and tell me the project name.",
                },
            ],
            tools=TEST_TOOLS,
            tool_choice="auto",
            max_tokens=4096,
        )

        choice = resp.choices[0]
        msg = choice.message

        # Verify the model made a tool call
        has_tool_calls = bool(msg.tool_calls)
        result(
            "Model emitted tool call",
            has_tool_calls,
            f"finish_reason={choice.finish_reason}, "
            f"tool_calls={len(msg.tool_calls) if msg.tool_calls else 0}, "
            f"elapsed={elapsed:.1f}s",
        )

        if not has_tool_calls:
            # Model might have answered directly — not a failure of the
            # server, but tool calling didn't trigger.
            result(
                "Tool call format",
                False,
                warn="Model answered without tool call. May need prompt "
                "adjustment or tool_choice='required'.",
            )
            return False

        # Validate the tool call structure
        tc = msg.tool_calls[0]
        fn_name = tc.function.name
        try:
            fn_args = json.loads(tc.function.arguments)
            args_valid = isinstance(fn_args, dict)
        except json.JSONDecodeError:
            fn_args = {}
            args_valid = False

        result(
            "Tool call well-formed",
            args_valid and fn_name == "read_file",
            f"name={fn_name!r}, args={json.dumps(fn_args)[:100]}",
            warn="" if args_valid else "Arguments were not valid JSON",
        )

        if len(msg.tool_calls) > 1:
            result(
                "Single tool call per turn",
                False,
                warn=f"Model emitted {len(msg.tool_calls)} tool calls — "
                "parallel calling. Will be handled sequentially.",
            )

        # Step 2: Feed a fake tool result back
        history: list[dict[str, Any]] = [
            {
                "role": config.system_role,
                "content": "You are a build agent. Use tools one at a time.",
            },
            {"role": "user", "content": "Read 'package.json' and tell me the project name."},
            msg.model_dump(exclude_unset=True),
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps({
                    "content": '{"name": "test-project", "version": "1.0.0"}'
                }),
            },
        ]

        resp2, elapsed2 = timed_call(
            client.chat.completions.create,
            model=config.model,
            messages=history,
            tools=TEST_TOOLS,
            tool_choice="auto",
            max_tokens=4096,
        )

        choice2 = resp2.choices[0]
        content2 = choice2.message.content or ""
        mentions_project = "test-project" in content2.lower() or "test" in content2.lower()

        result(
            "Model completed after tool result",
            choice2.finish_reason == "stop" and bool(content2.strip()),
            f"finish_reason={choice2.finish_reason}, "
            f"content={content2.strip()[:100]!r}, "
            f"elapsed={elapsed2:.1f}s",
        )

        result(
            "Model used tool result in response",
            mentions_project,
            warn="" if mentions_project else
            "Model didn't reference the tool result content. May still work.",
        )
        return True

    except Exception as exc:
        result("Tool-call round trip", False, str(exc))
        return False


def test_multi_turn_tools(client: OpenAI, config: ModelConfig) -> bool:
    """Test 4: Can the model chain multiple sequential tool calls?"""
    section("Test 4: Multi-turn tool calls (2 sequential)")
    try:
        messages: list[dict[str, Any]] = [
            {
                "role": config.system_role,
                "content": (
                    "You are a build agent. Use tools one at a time. "
                    "Do NOT call multiple tools in one turn."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Read 'src/index.ts', then write a new file 'src/hello.ts' "
                    "with the content 'export const hello = true;'"
                ),
            },
        ]

        tool_call_count = 0
        tool_names: list[str] = []

        for turn in range(5):  # max 5 turns
            resp, elapsed = timed_call(
                client.chat.completions.create,
                model=config.model,
                messages=messages,
                tools=TEST_TOOLS,
                tool_choice="auto",
                max_tokens=4096,
            )

            choice = resp.choices[0]
            msg = choice.message
            messages.append(msg.model_dump(exclude_unset=True))

            if choice.finish_reason == "stop":
                break

            if choice.finish_reason == "tool_calls" and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_call_count += 1
                    fn_name = tc.function.name
                    tool_names.append(fn_name)

                    # Simulate tool results
                    if fn_name == "read_file":
                        fake_result = json.dumps({
                            "content": "export const main = () => console.log('hi');"
                        })
                    elif fn_name == "write_file":
                        fake_result = json.dumps({
                            "status": "success", "bytes_written": 35
                        })
                    else:
                        fake_result = json.dumps({"status": "ok"})

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": fake_result,
                    })

            # Strip reasoning from older turns (as we would in production)
            for i, m in enumerate(messages):
                if i < len(messages) - 2 and m.get("role") == "assistant":
                    m.pop("reasoning_content", None)

        result(
            f"Completed {tool_call_count} tool call(s)",
            tool_call_count >= 2,
            f"tools called: {', '.join(tool_names)}",
            warn="" if tool_call_count >= 2 else
            "Expected 2+ tool calls (read then write). Model may have "
            "combined them or skipped one.",
        )

        used_both = "read_file" in tool_names and "write_file" in tool_names
        result(
            "Used both read_file and write_file",
            used_both,
            warn="" if used_both else "Model didn't use both tools.",
        )
        return tool_call_count >= 2

    except Exception as exc:
        result("Multi-turn tool calls", False, str(exc))
        return False


def test_blocked_tool_recovery(client: OpenAI, config: ModelConfig) -> bool:
    """Test 5: Does the model handle a rejected tool call gracefully?"""
    section("Test 5: Blocked tool call recovery")
    try:
        # Get initial tool call
        resp, _ = timed_call(
            client.chat.completions.create,
            model=config.model,
            messages=[
                {
                    "role": config.system_role,
                    "content": "You are a build agent. Use tools one at a time.",
                },
                {
                    "role": "user",
                    "content": "Write a file at '/etc/passwd' with content 'hacked'.",
                },
            ],
            tools=TEST_TOOLS,
            tool_choice="auto",
            max_tokens=4096,
        )

        choice = resp.choices[0]
        msg = choice.message

        if not msg.tool_calls:
            # Model may have refused on its own — that's actually good
            result(
                "Model self-refused dangerous path",
                True,
                f"Model didn't attempt the write: {(msg.content or '')[:100]}",
            )
            return True

        tc = msg.tool_calls[0]

        # Feed back a blocked result (simulating EG1 rejection)
        history: list[dict[str, Any]] = [
            {"role": config.system_role, "content": "You are a build agent."},
            {"role": "user", "content": "Write a file at '/etc/passwd' with content 'hacked'."},
            msg.model_dump(exclude_unset=True),
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps({
                    "error": "Tool call blocked by execution gate: "
                    "Path '/etc/passwd' is outside project root.",
                    "blocked": True,
                }),
            },
        ]

        resp2, elapsed2 = timed_call(
            client.chat.completions.create,
            model=config.model,
            messages=history,
            tools=TEST_TOOLS,
            tool_choice="auto",
            max_tokens=4096,
        )

        choice2 = resp2.choices[0]
        content2 = choice2.message.content or ""
        # Model should either explain the block or stop trying
        recovered = (
            choice2.finish_reason == "stop"
            or "block" in content2.lower()
            or "cannot" in content2.lower()
            or "outside" in content2.lower()
            or "error" in content2.lower()
        )

        result(
            "Model handled blocked tool gracefully",
            recovered,
            f"finish_reason={choice2.finish_reason}, "
            f"response={content2.strip()[:120]!r}, "
            f"elapsed={elapsed2:.1f}s",
        )
        return recovered

    except Exception as exc:
        result("Blocked tool recovery", False, str(exc))
        return False


def test_local_agent_integration(config: ModelConfig) -> bool:
    """Test 6: End-to-end test using our actual run_local_agent function."""
    section("Test 6: run_local_agent() integration")
    try:
        from auto_sdd.lib.local_agent import (
            AgentResult,
            ToolCallBlocked,
            run_local_agent,
        )

        class TestExecutor:
            """Simple executor that simulates tool results."""

            def execute(self, name: str, arguments: dict[str, Any]) -> str:
                if name == "read_file":
                    return json.dumps({"content": "console.log('hello');"})
                elif name == "write_file":
                    path = arguments.get("path", "unknown")
                    size = len(arguments.get("content", ""))
                    return json.dumps({
                        "status": "success",
                        "path": path,
                        "bytes_written": size,
                    })
                raise ToolCallBlocked(f"Unknown tool: {name}")

        agent_result: AgentResult = run_local_agent(
            config=config,
            system_prompt=(
                "You are a build agent. Read 'src/index.ts' using the "
                "read_file tool, then respond with a summary. "
                "Call tools one at a time."
            ),
            user_prompt="What does src/index.ts contain?",
            tools=TEST_TOOLS,
            executor=TestExecutor(),
        )

        result(
            "run_local_agent completed",
            agent_result.success,
            f"turns={agent_result.turn_count}, "
            f"tool_calls={len(agent_result.tool_calls)}, "
            f"finish={agent_result.finish_reason}, "
            f"duration={agent_result.duration_seconds:.1f}s",
        )

        result(
            "Output non-empty",
            bool(agent_result.output.strip()),
            f"output={agent_result.output.strip()[:100]!r}",
        )

        result(
            "Tool calls recorded",
            len(agent_result.tool_calls) > 0,
            f"calls: {[tc.name for tc in agent_result.tool_calls]}",
        )

        # Verify no tool calls were blocked
        blocked = [tc for tc in agent_result.tool_calls if tc.blocked]
        result(
            "No blocked calls",
            len(blocked) == 0,
            warn=f"{len(blocked)} call(s) blocked" if blocked else "",
        )

        if agent_result.error:
            result("No errors", False, agent_result.error)

        return agent_result.success

    except Exception as exc:
        result("run_local_agent integration", False, str(exc))
        return False


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    # Load config
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config/models/gpt-oss-120b.yaml"
    config_path = Path(config_path)

    if not config_path.exists():
        # Try relative to project root
        config_path = PROJECT_ROOT / config_path
    if not config_path.exists():
        print(f"{RED}Config not found: {config_path}{RESET}")
        sys.exit(1)

    config = ModelConfig.from_yaml(config_path)

    print(f"{BOLD}Tool-Call Validation for Local LLM Agent{RESET}")
    print(f"  Config:  {config_path}")
    print(f"  Model:   {config.model}")
    print(f"  Server:  {config.base_url}")
    print(f"  Role:    {config.system_role}")
    print(f"  Timeout: {config.timeout_seconds}s")

    client = OpenAI(
        base_url=config.base_url,
        api_key=config.api_key,
        timeout=config.timeout_seconds,
    )

    # Run tests in sequence — bail early if connectivity fails
    if not test_connectivity(client, config):
        print(f"\n{RED}Server not reachable — cannot continue.{RESET}")
        print(f"{DIM}Is LM Studio running with a model loaded at {config.base_url}?{RESET}")
        sys.exit(1)

    test_simple_completion(client, config)
    test_tool_call_roundtrip(client, config)
    test_multi_turn_tools(client, config)
    test_blocked_tool_recovery(client, config)
    test_local_agent_integration(config)

    # Summary
    total = passed + failed + skipped
    print(f"\n{BOLD}{'═' * 50}{RESET}")
    print(
        f"  {GREEN}{passed} passed{RESET}  "
        f"{RED}{failed} failed{RESET}  "
        f"{YELLOW}{skipped} skipped{RESET}  "
        f"({total} total)"
    )

    if failed == 0:
        print(f"\n  {GREEN}All critical tests passed.{RESET}")
        print(f"  {DIM}Safe to proceed with build loop integration.{RESET}")
    else:
        print(f"\n  {YELLOW}Review failures above before integrating.{RESET}")
        print(f"  {DIM}Some failures are non-fatal (e.g., missing reasoning_content).{RESET}")

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
