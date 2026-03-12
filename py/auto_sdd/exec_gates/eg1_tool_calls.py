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
import re
import subprocess
from pathlib import Path
from typing import Any

from auto_sdd.lib.local_agent import ToolCallBlocked

logger = logging.getLogger(__name__)

# ── Command safety ───────────────────────────────────────────────────────────

# [Fix 1]: First-token extraction for blocklist matching. Substring matching
# caused collisions ("dd" matched "git add", "su" matched "result").
# We now extract the first token and match against it, plus scan for
# dangerous tokens anywhere in the command with word-boundary awareness.

# Commands blocked by first token (the executable itself).
BLOCKED_FIRST_TOKENS: frozenset[str] = frozenset({
    # Destructive system commands
    "mkfs", "dd", "format", "fdisk", "parted",
    # System power
    "shutdown", "reboot", "halt", "poweroff", "init",
    # Network (no agent should fetch anything)
    "curl", "wget", "ssh", "scp", "rsync", "nc", "ncat", "netcat",
    "ftp", "sftp", "telnet",
    # Privilege escalation
    "sudo", "su", "doas",
    # Process management
    "kill", "killall", "pkill",
    # [Fix 5]: Additional dangerous commands
    "eval", "exec", "source",  # Shell execution indirection
    "env",  # Can leak environment variables or run commands
    "open",  # macOS: launch arbitrary apps
    "osascript",  # macOS: arbitrary AppleScript
    "xargs",  # Amplifies commands, hard to validate target
    "nohup",  # Background execution, escapes timeout
    "screen", "tmux",  # Session managers, escape sandbox
    "crontab", "at",  # Scheduled execution
    "launchctl",  # macOS service management
    "defaults",  # macOS preferences manipulation
})

# [Fix 2]: Block all rm -r / rm -rf patterns regardless of target.
# Agent should not recursively delete anything. If deletion is needed,
# a scoped delete_file tool can be added later.
_RM_RECURSIVE_PATTERN = re.compile(
    r'\brm\s+(-[a-zA-Z]*r[a-zA-Z]*\s|--recursive)', re.IGNORECASE
)

# [Fix 3]: Shell metacharacter / injection patterns.
# Catches command substitution, backgrounding, and common bypass tricks.
_SHELL_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\$\('), "command substitution $()"),
    (re.compile(r'`[^`]+`'), "backtick command substitution"),
    (re.compile(r'\|\s*bash'), "pipe to bash"),
    (re.compile(r'\|\s*sh\b'), "pipe to sh"),
    (re.compile(r'\|\s*zsh'), "pipe to zsh"),
    (re.compile(r'\|\s*python'), "pipe to python"),
    (re.compile(r'\|\s*node'), "pipe to node"),
    (re.compile(r'\|\s*perl'), "pipe to perl"),
    (re.compile(r'\|\s*ruby'), "pipe to ruby"),
    (re.compile(r'>\s*/dev/tcp'), "TCP redirect"),
    (re.compile(r'>\s*/dev/udp'), "UDP redirect"),
    (re.compile(r'\bbase64\s+(-d|--decode)'), "base64 decode (obfuscation)"),
    (re.compile(r'\\x[0-9a-fA-F]{2}'), "hex-escaped characters (obfuscation)"),
    (re.compile(r'\b(bash|sh|zsh)\s+-c\s'), "shell -c execution"),
    (re.compile(r'&\s*$'), "background execution (&)"),
    (re.compile(r';\s*\S'), "command chaining with semicolon"),
    (re.compile(r'&&\s*\S'), "command chaining with &&"),
    (re.compile(r'\|\|\s*\S'), "command chaining with ||"),
]

# [Fix 4]: Detect write-then-exec patterns.
# These file extensions, if written by write_file, could be executed
# by run_command. We track written files and block execution of scripts
# the agent just created within the project.
EXECUTABLE_EXTENSIONS: frozenset[str] = frozenset({
    ".sh", ".bash", ".zsh", ".py", ".rb", ".pl", ".js", ".ts",
})

# [Fix 6]: Block all chmod (not just 777). Agent should not change
# file permissions — that's an orchestrator concern.
# Also block chown/chgrp for the same reason.
BLOCKED_ANYWHERE_TOKENS: frozenset[str] = frozenset({
    "chmod", "chown", "chgrp",
})

# Command prefixes that are allowed. Anything not matching is blocked.
# Checked AFTER blocklist and injection checks pass.
ALLOWED_COMMAND_PREFIXES: tuple[str, ...] = (
    "npm ", "npx ", "node ",
    "tsc", "tsx",
    "git add", "git commit", "git status", "git diff", "git log",
    "git checkout", "git branch", "git rev-parse", "git show",
    "cat ", "ls ", "find ", "grep ", "head ", "tail ", "wc ",
    "mkdir ", "touch ", "cp ", "mv ",
    "echo ", "printf ",
    "python", "pip ",
    "test ", "[",  # shell test expressions
)


# ── Path safety ──────────────────────────────────────────────────────────────

# Paths that must never be written to.
BLOCKED_PATHS: tuple[str, ...] = (
    "/etc/", "/usr/", "/bin/", "/sbin/", "/var/",
    "/System/", "/Library/",
    "/tmp/",  # Temp dir writes could be used to stage exec payloads
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


def _extract_first_token(command: str) -> str:
    """Extract the first token (executable) from a command string.

    Handles common prefixes like env vars (FOO=bar cmd) by skipping
    them. Returns lowercase for consistent matching.
    """
    parts = command.strip().split()
    for part in parts:
        # Skip env var assignments (KEY=value)
        if "=" in part and not part.startswith("-"):
            continue
        return part.lower()
    return ""


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
    """Validate a shell command against all restriction layers.

    Check order (all must pass):
        1. First-token blocklist (exact match, not substring)
        2. rm -r / rm -rf pattern (any target)
        3. Shell injection / metacharacter patterns
        4. Blocked-anywhere tokens (chmod, chown, chgrp)
        5. Allowlist prefix match (if none match, blocked)

    Raises ToolCallBlocked on any violation.
    """
    cmd_stripped = command.strip()
    if not cmd_stripped:
        raise ToolCallBlocked("run_command: empty command")

    # [Fix 1]: First-token extraction — no more substring collisions
    first_token = _extract_first_token(cmd_stripped)
    if first_token in BLOCKED_FIRST_TOKENS:
        raise ToolCallBlocked(
            f"Blocked command: '{first_token}' is not permitted"
        )

    # [Fix 2]: Block all recursive rm regardless of target
    if _RM_RECURSIVE_PATTERN.search(cmd_stripped):
        raise ToolCallBlocked(
            "Recursive rm (rm -r / rm -rf) is not permitted. "
            "Use separate tool calls or a scoped delete_file tool."
        )

    # [Fix 3]: Shell injection / metacharacter detection
    for pattern, description in _SHELL_INJECTION_PATTERNS:
        if pattern.search(cmd_stripped):
            raise ToolCallBlocked(
                f"Shell injection detected: {description}. "
                "Use separate tool calls instead of chaining commands."
            )

    # [Fix 6]: Block chmod/chown/chgrp anywhere in command
    cmd_lower = cmd_stripped.lower()
    for token in BLOCKED_ANYWHERE_TOKENS:
        # Word-boundary match to avoid false positives
        if re.search(rf'\b{token}\b', cmd_lower):
            raise ToolCallBlocked(
                f"Command contains blocked operation: '{token}'. "
                "File permissions are managed by the orchestrator."
            )

    # Allowlist: command must start with an approved prefix
    allowed = any(
        cmd_stripped.startswith(prefix) or cmd_stripped == prefix.strip()
        for prefix in ALLOWED_COMMAND_PREFIXES
    )
    if not allowed:
        raise ToolCallBlocked(
            f"Command '{cmd_stripped[:80]}' does not match any allowed "
            f"prefix. Use one of: {', '.join(p.strip() for p in ALLOWED_COMMAND_PREFIXES[:10])}..."
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

    [Fix 4]: Tracks files written by the agent. If the agent writes a
    script file (.sh, .py, etc.) and then tries to execute it, the
    execution is blocked — prevents the write-then-exec bypass.
    """

    def __init__(
        self,
        project_root: Path,
        command_timeout: int = 60,
    ) -> None:
        self.project_root = project_root.resolve()
        self.command_timeout = command_timeout
        # [Fix 4]: Track files the agent has written this session
        self._written_files: set[str] = set()

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

            # [Fix 4]: Track written files for exec detection
            self._written_files.add(str(full_path))

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

        # [Fix 4]: Check for write-then-exec bypass.
        # If the agent wrote a script and now tries to execute it,
        # block it — the content of the script can't be validated.
        self._check_write_then_exec(command)

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

    def _check_write_then_exec(self, command: str) -> None:
        """[Fix 4]: Detect and block execution of agent-written scripts.

        If the agent wrote a file with an executable extension (.sh, .py,
        etc.) during this session and now tries to reference it in a
        command, block it. The script contents bypass our command
        validation — we validated the write_file content gate but the
        script could contain anything.

        Also blocks direct execution patterns like 'bash script.sh',
        'python script.py', './script.sh'.
        """
        if not self._written_files:
            return

        cmd_parts = command.strip().split()
        for part in cmd_parts:
            # Resolve the part as a potential file path
            candidate = part.lstrip("./")
            full_candidate = (self.project_root / candidate).resolve()
            full_str = str(full_candidate)

            if full_str in self._written_files:
                ext = Path(full_str).suffix.lower()
                if ext in EXECUTABLE_EXTENSIONS:
                    raise ToolCallBlocked(
                        f"Write-then-exec detected: agent wrote "
                        f"'{candidate}' ({ext}) and is now trying to "
                        f"execute it. Script contents cannot be validated."
                    )

        # Also check for npm script modification + execution.
        # If agent wrote package.json, running npm run <anything> could
        # execute arbitrary code via the scripts section.
        pkg_json = str(self.project_root / "package.json")
        if pkg_json in self._written_files:
            if command.strip().startswith("npm run"):
                raise ToolCallBlocked(
                    "Agent modified package.json and is now running "
                    "'npm run' — the scripts section may contain "
                    "arbitrary commands. Commit and review first."
                )
