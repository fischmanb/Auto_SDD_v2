"""Tests for local_agent.py — OpenAI-compatible agent loop."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from auto_sdd.lib.local_agent import (
    AgentResult,
    ToolCallBlocked,
    ToolCallRecord,
    _build_assistant_history_entry,
    _execute_with_gate,
    _parse_tool_arguments,
    _strip_older_reasoning,
    run_local_agent,
)
from auto_sdd.lib.model_config import ModelConfig


# ── Mock helpers ─────────────────────────────────────────────────────────────


def _make_tool_call(
    tc_id: str = "call_1",
    name: str = "write_file",
    arguments: str = '{"path": "a.txt", "content": "hi"}',
) -> MagicMock:
    tc = MagicMock()
    tc.id = tc_id
    tc.type = "function"
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


def _make_choice(
    finish_reason: str = "stop",
    content: str = "done",
    tool_calls: list | None = None,
    reasoning_content: str | None = None,
) -> MagicMock:
    choice = MagicMock()
    choice.finish_reason = finish_reason
    choice.message.content = content
    choice.message.tool_calls = tool_calls or []
    if reasoning_content is not None:
        choice.message.reasoning_content = reasoning_content
    else:
        # Simulate attribute not present
        del choice.message.reasoning_content
    return choice


def _make_response(choice: MagicMock) -> MagicMock:
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _cfg(**overrides: Any) -> ModelConfig:
    defaults = {
        "max_turns": 5,
        "timeout_seconds": 10,
        "strip_reasoning_older_turns": False,
    }
    defaults.update(overrides)
    return ModelConfig(**defaults)


class FakeExecutor:
    """ToolExecutor that records calls and returns canned results."""

    def __init__(self, results: dict[str, str] | None = None, block: str = ""):
        self._results = results or {}
        self._block = block
        self.calls: list[tuple[str, dict]] = []

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        self.calls.append((name, arguments))
        if self._block:
            raise ToolCallBlocked(self._block)
        return self._results.get(name, '{"ok": true}')


# ── Dataclass tests ──────────────────────────────────────────────────────────


class TestToolCallRecord:
    def test_to_dict_truncates_result(self) -> None:
        rec = ToolCallRecord(turn=0, name="run_command", arguments={"command": "ls"}, result="x" * 600)
        d = rec.to_dict()
        assert len(d["result"]) == 500
        assert d["turn"] == 0
        assert d["blocked"] is False

    def test_to_dict_blocked(self) -> None:
        rec = ToolCallRecord(turn=1, name="write_file", arguments={}, result="", blocked=True, error="nope")
        d = rec.to_dict()
        assert d["blocked"] is True
        assert d["error"] == "nope"


class TestAgentResult:
    def test_success_true(self) -> None:
        r = AgentResult(finish_reason="stop", error="")
        assert r.success is True

    def test_success_false_on_error(self) -> None:
        r = AgentResult(finish_reason="stop", error="oops")
        assert r.success is False

    def test_success_false_on_finish_reason(self) -> None:
        r = AgentResult(finish_reason="length", error="")
        assert r.success is False


    def test_to_dict_truncates_output(self) -> None:
        r = AgentResult(output="y" * 3000, turn_count=3, finish_reason="stop")
        d = r.to_dict()
        assert len(d["output"]) == 2000
        assert d["turn_count"] == 3


# ── Helper tests ─────────────────────────────────────────────────────────────


class TestParseToolArguments:
    def test_valid_dict(self) -> None:
        result = _parse_tool_arguments("write_file", '{"path": "a.txt"}')
        assert result == {"path": "a.txt"}

    def test_non_dict_wrapped(self) -> None:
        result = _parse_tool_arguments("run_command", '"ls"')
        assert "_parsed" in result
        assert "_raw" in result

    def test_invalid_json(self) -> None:
        result = _parse_tool_arguments("write_file", "{bad json")
        assert "_raw" in result
        assert "_parse_error" in result


class TestExecuteWithGate:
    def test_success(self) -> None:
        executor = FakeExecutor(results={"write_file": '{"written": true}'})
        rec = ToolCallRecord(turn=0, name="write_file", arguments={}, result="")
        out = _execute_with_gate(executor, "write_file", {}, rec)
        assert out == '{"written": true}'
        assert not rec.blocked


    def test_blocked(self) -> None:
        executor = FakeExecutor(block="path denied")
        rec = ToolCallRecord(turn=0, name="write_file", arguments={}, result="")
        out = _execute_with_gate(executor, "write_file", {}, rec)
        assert rec.blocked is True
        parsed = json.loads(out)
        assert parsed["blocked"] is True

    def test_general_exception(self) -> None:
        executor = MagicMock()
        executor.execute.side_effect = RuntimeError("disk full")
        rec = ToolCallRecord(turn=0, name="write_file", arguments={}, result="")
        out = _execute_with_gate(executor, "write_file", {}, rec)
        assert "disk full" in rec.error
        parsed = json.loads(out)
        assert "disk full" in parsed["error"]


class TestStripOlderReasoning:
    def test_strips_all_but_last(self) -> None:
        msgs = [
            {"role": "developer", "content": "sys"},
            {"role": "assistant", "content": "a1", "reasoning_content": "r1"},
            {"role": "tool", "tool_call_id": "1", "content": "ok"},
            {"role": "assistant", "content": "a2", "reasoning_content": "r2"},
        ]
        _strip_older_reasoning(msgs)
        assert "reasoning_content" not in msgs[1]
        assert msgs[3]["reasoning_content"] == "r2"

    def test_single_assistant_no_strip(self) -> None:
        msgs = [
            {"role": "assistant", "content": "a1", "reasoning_content": "r1"},
        ]
        _strip_older_reasoning(msgs)
        assert msgs[0]["reasoning_content"] == "r1"


class TestBuildAssistantHistoryEntry:
    def test_basic_message(self) -> None:
        msg = MagicMock()
        msg.content = "hello"
        msg.tool_calls = []
        del msg.reasoning_content  # not present
        entry = _build_assistant_history_entry(msg)
        assert entry["role"] == "assistant"
        assert entry["content"] == "hello"
        assert "reasoning_content" not in entry
        assert "tool_calls" not in entry

    def test_with_reasoning(self) -> None:
        msg = MagicMock()
        msg.content = "answer"
        msg.tool_calls = []
        msg.reasoning_content = "thinking..."
        entry = _build_assistant_history_entry(msg)
        assert entry["reasoning_content"] == "thinking..."

    def test_with_tool_calls(self) -> None:
        tc = _make_tool_call(tc_id="c1", name="read_file", arguments='{"path": "x"}')
        msg = MagicMock()
        msg.content = None
        msg.tool_calls = [tc]
        del msg.reasoning_content
        entry = _build_assistant_history_entry(msg)
        assert len(entry["tool_calls"]) == 1
        assert entry["tool_calls"][0]["id"] == "c1"
        assert entry["tool_calls"][0]["function"]["name"] == "read_file"


# ── run_local_agent tests ────────────────────────────────────────────────────


class TestRunLocalAgent:
    """Tests for the main agent loop. OpenAI client is patched."""

    TOOLS = [{"type": "function", "function": {"name": "write_file", "parameters": {}}}]

    @patch("auto_sdd.lib.local_agent.OpenAI")
    def test_stop_first_turn(self, mock_openai_cls: MagicMock) -> None:
        client = mock_openai_cls.return_value
        client.chat.completions.create.return_value = _make_response(
            _make_choice(finish_reason="stop", content="all done")
        )
        result = run_local_agent(_cfg(), "sys", "task", self.TOOLS, FakeExecutor())
        assert result.success
        assert result.output == "all done"
        assert result.turn_count == 1
        assert result.finish_reason == "stop"

    @patch("auto_sdd.lib.local_agent.OpenAI")
    def test_tool_call_then_stop(self, mock_openai_cls: MagicMock) -> None:
        tc = _make_tool_call(name="write_file", arguments='{"path": "f.txt", "content": "x"}')
        client = mock_openai_cls.return_value
        client.chat.completions.create.side_effect = [
            _make_response(_make_choice(finish_reason="tool_calls", content=None, tool_calls=[tc])),
            _make_response(_make_choice(finish_reason="stop", content="wrote it")),
        ]
        executor = FakeExecutor(results={"write_file": '{"ok": true}'})
        result = run_local_agent(_cfg(), "sys", "write a file", self.TOOLS, executor)
        assert result.success
        assert result.output == "wrote it"
        assert result.turn_count == 2
        assert len(result.tool_calls) == 1
        assert len(executor.calls) == 1


    @patch("auto_sdd.lib.local_agent.OpenAI")
    def test_blocked_tool_call_fed_back(self, mock_openai_cls: MagicMock) -> None:
        tc = _make_tool_call(name="write_file", arguments='{"path": "/etc/passwd", "content": "x"}')
        client = mock_openai_cls.return_value
        client.chat.completions.create.side_effect = [
            _make_response(_make_choice(finish_reason="tool_calls", content=None, tool_calls=[tc])),
            _make_response(_make_choice(finish_reason="stop", content="ok fixed")),
        ]
        executor = FakeExecutor(block="path outside project")
        result = run_local_agent(_cfg(), "sys", "task", self.TOOLS, executor)
        assert result.success
        assert result.tool_calls[0].blocked is True
        # Verify blocked result was fed back as tool message
        call_args = client.chat.completions.create.call_args_list[1]
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert "blocked" in tool_msgs[0]["content"]

    @patch("auto_sdd.lib.local_agent.OpenAI")
    def test_length_finish_reason(self, mock_openai_cls: MagicMock) -> None:
        client = mock_openai_cls.return_value
        client.chat.completions.create.return_value = _make_response(
            _make_choice(finish_reason="length", content="partial")
        )
        result = run_local_agent(_cfg(), "sys", "task", self.TOOLS, FakeExecutor())
        assert not result.success
        assert result.finish_reason == "length"
        assert result.output == "partial"


    @patch("auto_sdd.lib.local_agent.OpenAI")
    def test_max_turns_exhausted(self, mock_openai_cls: MagicMock) -> None:
        tc = _make_tool_call()
        client = mock_openai_cls.return_value
        # Every turn returns a tool call — never stops
        client.chat.completions.create.return_value = _make_response(
            _make_choice(finish_reason="tool_calls", content=None, tool_calls=[tc])
        )
        result = run_local_agent(_cfg(max_turns=3), "sys", "task", self.TOOLS, FakeExecutor())
        assert not result.success
        assert result.finish_reason == "max_turns"
        assert result.turn_count == 3

    @patch("auto_sdd.lib.local_agent.OpenAI")
    def test_api_error(self, mock_openai_cls: MagicMock) -> None:
        client = mock_openai_cls.return_value
        client.chat.completions.create.side_effect = ConnectionError("refused")
        result = run_local_agent(_cfg(), "sys", "task", self.TOOLS, FakeExecutor())
        assert not result.success
        assert result.finish_reason == "error"
        assert "refused" in result.error

    @patch("auto_sdd.lib.local_agent.OpenAI")
    def test_no_tools(self, mock_openai_cls: MagicMock) -> None:
        client = mock_openai_cls.return_value
        client.chat.completions.create.return_value = _make_response(
            _make_choice(finish_reason="stop", content="no tools needed")
        )
        result = run_local_agent(_cfg(), "sys", "task", None, FakeExecutor())
        assert result.success
        # tools and tool_choice should not appear in kwargs
        kwargs = client.chat.completions.create.call_args.kwargs
        assert "tools" not in kwargs
        assert "tool_choice" not in kwargs


    @patch("auto_sdd.lib.local_agent.OpenAI")
    def test_developer_role_in_messages(self, mock_openai_cls: MagicMock) -> None:
        client = mock_openai_cls.return_value
        client.chat.completions.create.return_value = _make_response(
            _make_choice(finish_reason="stop", content="ok")
        )
        run_local_agent(_cfg(use_developer_role=True), "sys prompt", "task", None, FakeExecutor())
        kwargs = client.chat.completions.create.call_args.kwargs
        msgs = kwargs["messages"]
        assert msgs[0]["role"] == "developer"
        assert msgs[0]["content"] == "sys prompt"

    @patch("auto_sdd.lib.local_agent.OpenAI")
    def test_system_role_in_messages(self, mock_openai_cls: MagicMock) -> None:
        client = mock_openai_cls.return_value
        client.chat.completions.create.return_value = _make_response(
            _make_choice(finish_reason="stop", content="ok")
        )
        run_local_agent(_cfg(use_developer_role=False), "sys prompt", "task", None, FakeExecutor())
        kwargs = client.chat.completions.create.call_args.kwargs
        msgs = kwargs["messages"]
        assert msgs[0]["role"] == "system"

    @patch("auto_sdd.lib.local_agent.OpenAI")
    def test_strip_reasoning_integration(self, mock_openai_cls: MagicMock) -> None:
        """Reasoning from older turns is stripped when config enabled.

        Needs 2 tool-call turns so strip fires (requires >1 assistant msg).
        We capture message snapshots because the messages list is mutated
        in-place after each call (shared reference in call_args).
        """
        tc1 = _make_tool_call(tc_id="c1")
        tc2 = _make_tool_call(tc_id="c2")
        client = mock_openai_cls.return_value

        responses = [
            _make_response(_make_choice(
                finish_reason="tool_calls", content=None,
                tool_calls=[tc1], reasoning_content="think1",
            )),
            _make_response(_make_choice(
                finish_reason="tool_calls", content=None,
                tool_calls=[tc2], reasoning_content="think2",
            )),
            _make_response(_make_choice(finish_reason="stop", content="done")),
        ]
        snapshots: list[list[dict]] = []

        def capture_and_respond(**kwargs: Any) -> MagicMock:
            import copy
            snapshots.append(copy.deepcopy(kwargs["messages"]))
            return responses.pop(0)

        client.chat.completions.create.side_effect = capture_and_respond

        result = run_local_agent(
            _cfg(strip_reasoning_older_turns=True), "sys", "task", self.TOOLS, FakeExecutor()
        )
        assert result.success
        assert len(snapshots) == 3
        # Third call's snapshot: first assistant msg should have reasoning stripped
        assistant_msgs = [m for m in snapshots[2] if m.get("role") == "assistant"]
        assert len(assistant_msgs) == 2
        assert "reasoning_content" not in assistant_msgs[0]
        # Second (most recent) assistant msg keeps reasoning
        assert assistant_msgs[1].get("reasoning_content") == "think2"


    @patch("auto_sdd.lib.local_agent.OpenAI")
    def test_multiple_tool_calls_one_turn(self, mock_openai_cls: MagicMock) -> None:
        tc1 = _make_tool_call(tc_id="c1", name="read_file", arguments='{"path": "a.txt"}')
        tc2 = _make_tool_call(tc_id="c2", name="write_file", arguments='{"path": "b.txt", "content": "x"}')
        client = mock_openai_cls.return_value
        client.chat.completions.create.side_effect = [
            _make_response(_make_choice(finish_reason="tool_calls", content=None, tool_calls=[tc1, tc2])),
            _make_response(_make_choice(finish_reason="stop", content="both done")),
        ]
        executor = FakeExecutor()
        result = run_local_agent(_cfg(), "sys", "task", self.TOOLS, executor)
        assert result.success
        assert len(result.tool_calls) == 2
        assert len(executor.calls) == 2

    @patch("auto_sdd.lib.local_agent.OpenAI")
    def test_extra_params_forwarded(self, mock_openai_cls: MagicMock) -> None:
        client = mock_openai_cls.return_value
        client.chat.completions.create.return_value = _make_response(
            _make_choice(finish_reason="stop", content="ok")
        )
        run_local_agent(
            _cfg(extra_params={"reasoning_effort": "high"}),
            "sys", "task", None, FakeExecutor(),
        )
        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs["reasoning_effort"] == "high"

    @patch("auto_sdd.lib.local_agent.OpenAI")
    def test_duration_populated(self, mock_openai_cls: MagicMock) -> None:
        client = mock_openai_cls.return_value
        client.chat.completions.create.return_value = _make_response(
            _make_choice(finish_reason="stop", content="ok")
        )
        result = run_local_agent(_cfg(), "sys", "task", None, FakeExecutor())
        assert result.duration_seconds >= 0.0

    @patch("auto_sdd.lib.local_agent.OpenAI")
    def test_unexpected_finish_reason_continues(self, mock_openai_cls: MagicMock) -> None:
        """Unknown finish_reason doesn't crash — loop continues."""
        client = mock_openai_cls.return_value
        client.chat.completions.create.side_effect = [
            _make_response(_make_choice(finish_reason="content_filter", content=None)),
            _make_response(_make_choice(finish_reason="stop", content="recovered")),
        ]
        result = run_local_agent(_cfg(), "sys", "task", self.TOOLS, FakeExecutor())
        assert result.success
        assert result.turn_count == 2
