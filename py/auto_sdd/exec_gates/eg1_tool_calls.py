"""EG1: Tool Call ExecGate — primary intercept at the agent boundary.

Implements the ToolExecutor protocol from local_agent.py. Every tool
call the agent proposes passes through here before execution. The gate
validates path restrictions, command allowlists, and scope boundaries,
then either executes the tool or raises ToolCallBlocked.

The agent proposes; the gate disposes.

This is the core ExecGate pattern from the V2 plan:
    model output → parse tool call → [EG1 intercept] → execute or block
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from auto_sdd.lib.local_agent import ToolCallBlocked

logger = logging.getLogger(__name__)


# ── Command safety ───────────────────────────────────────────────────────────

# Commands that are never allowed regardless of context.
BLOCKED_COMMANDS: frozenset[str] = frozenset({
    "rm -rf /", "rm -rf /*", "mkfs", "dd", "format",
    "shutdown", "reboot", "halt", "poweroff",
    "curl", "wget",  # No network fetches from agent
    "ssh", "scp", "rsync",  # No remote operations
    "sudo", "su", "chmod 777",  # No privilege escalation
    "kill", "killall", "pkill",  # No process management
})

# Command prefixes that are allowed. Anything not matching is blocked.
ALLOWED_COMMAND_PREFIXES: tuple[str, ...] = (
    "npm ", "npx ", "node ",
    "tsc", "tsx",
    "git add", "git commit", "git status", "git diff", "git log",
    "git checkout", "git branch",
    "cat ", "ls ", "find ", "grep ", "head ", "tail ", "wc ",
    "mkdir ", "touch ", "cp ",
    "echo ", "printf ",
    "cd ",
    "python", "pip ",
    "test ", "[",  # shell test expressions
)


# ── Path safety ──────────────────────────────────────────────────────────────

# Paths that must never be written to.
BLOCKED_PATHS: tuple[str, ...] = (
    "/etc/", "/usr/", "/bin/", "/sbin/", "/var/",
    "/System/", "/Library/",
    ".env", ".env.local",  # No credential overwrites
    ".git/",  # No direct git internals manipulation
)


def _is_path_within_project(path_str: str, project_root: Path) -> bool:
    """Check if a path resolves within the project root."""
    try:
        resolved = (project_root / path_str).resolve()
        resolved.relative_to(project_root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _validate_path(path_str: str, project_root: Path) -> None:
    """Validate a file path against restrictions. Raises ToolCallBlocked."""
    for blocked in BLOCKED_PATHS:
        if path_str.startswith(blocked) or f"/{blocked}" in path_str:
            raise ToolCallBlocked(
                f"Path '{path_str}' matches blocked pattern '{blocked}'"
            )

    if path_str.startswith("/") or ".." in path_str:
        if not _is_path_within_project(path_str, project_root):
            raise ToolCallBlocked(
                f"Path '{path_str}' resolves outside project root "
                f"'{project_root}'"
            )


def _validate_command(command: str) -> None:
    """Validate a shell command against restrictions. Raises ToolCallBlocked."""
    cmd_lower = command.strip().lower()

    # Check explicit blocks
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            raise ToolCallBlocked(
                f"Command contains blocked pattern: '{blocked}'"
            )

    # Check against allowlist
    cmd_trimmed = command.strip()
    allowed = any(
        cmd_trimmed.startswith(prefix) or cmd_trimmed == prefix.strip()
        for prefix in ALLOWED_COMMAND_PREFIXES
    )

    if not allowed:
        raise ToolCallBlocked(
            f"Command '{cmd_trimmed[:80]}' does not match any allowed "
            f"prefix. Allowed: {', '.join(p.strip() for p in ALLOWED_COMMAND_PREFIXES[:10])}..."
        )


# ── Executor ─────────────────────────────────────────────────────────────────


class BuildAgentExecutor:
    """ToolExecutor implementation for the build agent.

    Validates every tool call against path and command restrictions,
    then executes within the project sandbox. This is the EG1 intercept
    — the agent proposes, this class disposes.

    Supported tools:
        write_file(path, content)  — Write content to a file
        read_file(path)            — Read a file's contents
        run_command(command)        — Execute a shell command
    """

    def __init__(
        self,
        project_root: Path,
        command_timeout: int = 60,
    ) -> None:
        self.project_root = project_root.resolve()
        self.command_timeout = command_timeout

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Validate and execute a tool call.

        This method satisfies the ToolExecutor protocol from local_agent.py.
        Returns a JSON string result on success.
        Raises ToolCallBlocked on validation failure.
        """
        if "_parse_error" in arguments:
            raise ToolCallBlocked(
                f"Cannot execute {name}: malformed arguments — "
                f"{arguments.get('_parse_error', 'unknown parse error')}"
            )

        if name == "write_file":
            return self._exec_write_file(arguments)
        elif name == "read_file":
            return self._exec_read_file(arguments)
        elif name == "run_command":
            return self._exec_run_command(arguments)
        else:
            raise ToolCallBlocked(f"Unknown tool: '{name}'")

    def _exec_write_file(self, args: dict[str, Any]) -> str:
        """Gate + execute: write_file(path, content)."""
        path_str = args.get("path", "")
        content = args.get("content", "")

        if not path_str:
            raise ToolCallBlocked("write_file: 'path' is required")
        if not isinstance(content, str):
            raise ToolCallBlocked("write_file: 'content' must be a string")

        _validate_path(path_str, self.project_root)

        # Resolve within project
        full_path = (self.project_root / path_str).resolve()

        # Final containment check
        if not _is_path_within_project(path_str, self.project_root):
            raise ToolCallBlocked(
                f"write_file: resolved path '{full_path}' escapes project root"
            )

        # Execute
        try:
            os.makedirs(full_path.parent, exist_ok=True)
            full_path.write_text(content)
            logger.debug("EG1 write_file: %s (%d bytes)", path_str, len(content))
            return json.dumps({
                "status": "success",
                "path": path_str,
                "bytes_written": len(content),
            })
        except OSError as exc:
            return json.dumps({"error": f"Write failed: {exc}"})

    def _exec_read_file(self, args: dict[str, Any]) -> str:
        """Gate + execute: read_file(path)."""
        path_str = args.get("path", "")

        if not path_str:
            raise ToolCallBlocked("read_file: 'path' is required")

        _validate_path(path_str, self.project_root)

        full_path = (self.project_root / path_str).resolve()

        if not _is_path_within_project(path_str, self.project_root):
            raise ToolCallBlocked(
                f"read_file: resolved path '{full_path}' escapes project root"
            )

        try:
            content = full_path.read_text()
            logger.debug("EG1 read_file: %s (%d bytes)", path_str, len(content))
            return json.dumps({
                "content": content[:50000],  # Cap at 50KB to stay in context
                "path": path_str,
                "size": len(content),
                "truncated": len(content) > 50000,
            })
        except FileNotFoundError:
            return json.dumps({"error": f"File not found: {path_str}"})
        except OSError as exc:
            return json.dumps({"error": f"Read failed: {exc}"})

    def _exec_run_command(self, args: dict[str, Any]) -> str:
        """Gate + execute: run_command(command)."""
        command = args.get("command", "")

        if not command:
            raise ToolCallBlocked("run_command: 'command' is required")
        if not isinstance(command, str):
            raise ToolCallBlocked("run_command: 'command' must be a string")

        _validate_command(command)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.command_timeout,
                cwd=str(self.project_root),
            )
            logger.debug(
                "EG1 run_command: %s (rc=%d)",
                command[:80], result.returncode,
            )
            return json.dumps({
                "stdout": result.stdout[:4000],
                "stderr": result.stderr[:2000],
                "returncode": result.returncode,
            })
        except subprocess.TimeoutExpired:
            return json.dumps({
                "error": f"Command timed out after {self.command_timeout}s",
                "returncode": -1,
            })
        except OSError as exc:
            return json.dumps({"error": f"Command failed: {exc}"})
