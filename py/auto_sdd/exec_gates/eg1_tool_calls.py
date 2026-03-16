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

# Commands blocked by first token (the executable itself).
# Matched via _extract_first_token() — no substring collisions.
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
    # Shell execution indirection
    "eval", "exec", "source",
    # Environment manipulation
    "env", "export",
    # macOS specific
    "open", "osascript", "launchctl", "defaults",
    # Amplification / escape
    "xargs", "nohup", "screen", "tmux",
    # Scheduled execution
    "crontab", "at",
})

# Block all recursive rm regardless of target.
_RM_RECURSIVE_PATTERN = re.compile(
    r'\brm\s+(-[a-zA-Z]*r[a-zA-Z]*\s|--recursive)', re.IGNORECASE
)

# Shell injection / metacharacter patterns.
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
    (re.compile(r'\\x[0-9a-fA-F]{2}'), "hex-escaped characters"),
    (re.compile(r'\b(bash|sh|zsh)\s+-c\s'), "shell -c execution"),
    (re.compile(r'&\s*$'), "background execution (&)"),
    (re.compile(r';\s*\S'), "command chaining with semicolon"),
    (re.compile(r'&&\s*\S'), "command chaining with &&"),
    (re.compile(r'\|\|\s*\S'), "command chaining with ||"),
]

# Tokens blocked anywhere in command via word-boundary regex.
BLOCKED_ANYWHERE_TOKENS: frozenset[str] = frozenset({
    "chmod", "chown", "chgrp",
})

# Extensions that flag a file as executable for write-then-exec detection.
EXECUTABLE_EXTENSIONS: frozenset[str] = frozenset({
    ".sh", ".bash", ".zsh", ".py", ".rb", ".pl", ".js", ".ts",
})

# Git subcommands the agent is allowed to use.
# Everything else (push, merge, rebase, reset --hard, etc.) is blocked.
ALLOWED_GIT_SUBCOMMANDS: frozenset[str] = frozenset({
    "add", "commit", "status", "diff", "log", "show",
    "rev-parse", "branch",
})

# Git subcommands that are never allowed from the agent.
# Explicit blocklist for clarity — even if not in allowlist,
# these get a specific error message explaining why.
BLOCKED_GIT_SUBCOMMANDS: dict[str, str] = {
    "push": "Pushes are managed by the orchestrator, not the agent.",
    "merge": "Merges are managed by the orchestrator.",
    "rebase": "Rebases are managed by the orchestrator.",
    "reset": "Resets are managed by the orchestrator's retry logic.",
    "checkout": "Branch switching is managed by the orchestrator.",
    "switch": "Branch switching is managed by the orchestrator.",
    "stash": "Stashing is managed by the orchestrator.",
    "pull": "Pulls are managed by the orchestrator.",
    "fetch": "Fetches are managed by the orchestrator.",
    "remote": "Remote configuration is not permitted.",
    "config": "Git config changes are not permitted.",
    "clean": "git clean is managed by the orchestrator.",
}

# Base commands that are always allowed (non-runtime, non-git, non-npm).
# These are filesystem inspection and basic shell utilities.
ALLOWED_BASE_COMMANDS: tuple[str, ...] = (
    "cat ", "ls ", "find ", "grep ", "head ", "tail ", "wc ",
    "mkdir ", "touch ", "cp ", "mv ",
    "echo ", "printf ",
    "test ", "[",
)


# ── Path safety ──────────────────────────────────────────────────────────────

BLOCKED_PATHS: tuple[str, ...] = (
    "/etc/", "/usr/", "/bin/", "/sbin/", "/var/",
    "/System/", "/Library/", "/tmp/",
    ".git/",
)

# Paths blocked by exact filename match (not prefix).
# These are project-level sensitive files the agent must not overwrite.
BLOCKED_EXACT_FILENAMES: frozenset[str] = frozenset({
    ".env", ".env.local", ".env.production", ".env.staging",
    ".npmrc",  # Could inject registry URLs or auth tokens
    ".yarnrc", ".yarnrc.yml",  # Same risk as .npmrc
    ".netrc",  # Network credentials
})


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

    Handles env var assignments (FOO=bar cmd) by skipping them.
    Returns lowercase for consistent matching.
    """
    parts = command.strip().split()
    for part in parts:
        if "=" in part and not part.startswith("-"):
            continue
        return part.lower()
    return ""


def _validate_path(path_str: str, project_root: Path) -> None:
    """Validate a file path against restrictions. Raises ToolCallBlocked."""
    # Prefix-based blocks (system directories)
    for blocked in BLOCKED_PATHS:
        if path_str.startswith(blocked) or f"/{blocked}" in path_str:
            raise ToolCallBlocked(
                f"Path '{path_str}' matches blocked pattern '{blocked}'"
            )

    # Exact filename blocks (sensitive project files)
    filename = Path(path_str).name
    if filename in BLOCKED_EXACT_FILENAMES:
        raise ToolCallBlocked(
            f"Path '{path_str}' targets protected file '{filename}'"
        )

    # Build cache tampering
    if "node_modules/.cache" in path_str:
        raise ToolCallBlocked(
            f"Path '{path_str}' targets build cache (node_modules/.cache)"
        )

    # Containment check for absolute paths or parent traversal
    if path_str.startswith("/") or ".." in path_str:
        if not _is_path_within_project(path_str, project_root):
            raise ToolCallBlocked(
                f"Path '{path_str}' resolves outside project root "
                f"'{project_root}'"
            )


# ── Project introspection ────────────────────────────────────────────────────


def _parse_package_json(project_root: Path) -> dict[str, Any]:
    """Parse package.json for npm/npx allowlist derivation.

    Returns dict with:
        scripts: set of script names from "scripts"
        dev_deps: set of devDependency package names
        deps: set of dependency package names
    """
    pkg_path = project_root / "package.json"
    result: dict[str, Any] = {"scripts": set(), "dev_deps": set(), "deps": set()}

    if not pkg_path.exists():
        return result

    try:
        data = json.loads(pkg_path.read_text())
        if isinstance(data.get("scripts"), dict):
            result["scripts"] = set(data["scripts"].keys())
        if isinstance(data.get("devDependencies"), dict):
            result["dev_deps"] = set(data["devDependencies"].keys())
        if isinstance(data.get("dependencies"), dict):
            result["deps"] = set(data["dependencies"].keys())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to parse package.json: %s", exc)

    return result


# Map from runtime identifier to the command tokens it enables.
# The executor accepts allowed_runtimes as a set of these identifiers.
RUNTIME_COMMAND_TOKENS: dict[str, frozenset[str]] = {
    "node": frozenset({"node", "npm", "npx", "tsc", "tsx"}),
    "python": frozenset({"python", "python3", "pip", "pip3", "pytest", "mypy", "ruff", "black", "flake8"}),
    "rust": frozenset({"cargo", "rustc", "rustfmt", "clippy"}),
    "go": frozenset({"go"}),
    "java": frozenset({"java", "javac", "mvn", "gradle"}),
    "ruby": frozenset({"ruby", "gem", "bundle", "bundler", "rake"}),
    "php": frozenset({"php", "composer"}),
    "dotnet": frozenset({"dotnet"}),
    "swift": frozenset({"swift", "swiftc", "xcodebuild"}),
}


def detect_project_runtimes(project_root: Path) -> set[str]:
    """Auto-detect project runtimes from marker files.

    Returns a set of runtime identifiers (keys from RUNTIME_COMMAND_TOKENS).
    This is a fallback — prefer explicit allowed_runtimes from config/spec.
    """
    markers: dict[str, list[str]] = {
        "node": ["package.json", "tsconfig.json", ".nvmrc"],
        "python": ["pyproject.toml", "requirements.txt", "setup.py", "Pipfile"],
        "rust": ["Cargo.toml"],
        "go": ["go.mod"],
        "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "ruby": ["Gemfile"],
        "php": ["composer.json"],
        "dotnet": ["*.csproj", "*.fsproj", "*.sln"],
        "swift": ["Package.swift"],
    }

    detected: set[str] = set()
    for runtime, files in markers.items():
        for pattern in files:
            if "*" in pattern:
                if list(project_root.glob(pattern)):
                    detected.add(runtime)
                    break
            elif (project_root / pattern).exists():
                detected.add(runtime)
                break

    if detected:
        logger.info("Detected project runtimes: %s", ", ".join(sorted(detected)))
    else:
        logger.warning("No project runtimes detected from marker files")

    return detected


# ── Command argument containment ─────────────────────────────────────────────

# Commands whose arguments should be checked for path containment.
# If the agent runs `cat /etc/passwd` or `grep -r secret ~/other-project/`,
# the path arguments must resolve within project_root.
_PATH_ARGUMENT_COMMANDS: frozenset[str] = frozenset({
    "cat", "ls", "find", "grep", "head", "tail", "wc",
    "cp", "mv", "mkdir", "touch",
})


def _validate_command_arguments(
    command: str, project_root: Path
) -> None:
    """Check that file path arguments in commands stay within project_root.

    Extracts non-flag arguments from commands that operate on files
    and validates each against project containment. This prevents the
    agent from using allowed commands (cat, grep, etc.) to read or
    manipulate files outside the project.

    Raises ToolCallBlocked if any argument resolves outside project_root.
    """
    parts = command.strip().split()
    if not parts:
        return

    first_token = parts[0].lower()
    if first_token not in _PATH_ARGUMENT_COMMANDS:
        return

    for arg in parts[1:]:
        # Skip flags
        if arg.startswith("-"):
            continue

        # Skip glob patterns (the shell expands them relative to cwd,
        # which is project_root, so they're contained)
        if "*" in arg or "?" in arg:
            continue

        # Check if this looks like a path that could escape
        is_suspicious = (
            arg.startswith("/")
            or arg.startswith("~")
            or ".." in arg
            or arg.startswith("$")  # Variable expansion
        )

        if not is_suspicious:
            continue

        # Resolve and check containment
        if arg.startswith("~"):
            # Expand ~ to actual home dir for checking
            expanded = Path(arg).expanduser()
        else:
            expanded = Path(arg)

        # Resolve relative to project_root
        if not expanded.is_absolute():
            expanded = project_root / expanded

        try:
            expanded.resolve().relative_to(project_root.resolve())
        except (ValueError, OSError):
            raise ToolCallBlocked(
                f"Command argument '{arg}' resolves outside project root. "
                f"All file operations must stay within '{project_root}'."
            )


# ── Command validation (layered) ─────────────────────────────────────────────


def _validate_command_layers(
    command: str,
    allowed_runtime_tokens: frozenset[str],
    allowed_npm_scripts: frozenset[str],
    allowed_npx_packages: frozenset[str],
    allowed_branch: str,
    project_root: Path,
) -> None:
    """Validate a shell command against all restriction layers.

    Check order (all must pass):
        1. First-token blocklist
        2. rm -r / rm -rf pattern
        3. Shell injection / metacharacter patterns
        4. Blocked-anywhere tokens (chmod, chown, chgrp)
        5. Command argument path containment
        6. Git subcommand + branch validation
        7. npm/npx scope validation
        8. Runtime command validation
        9. Base command allowlist (fallback)

    Raises ToolCallBlocked on any violation.
    """
    cmd_stripped = command.strip()
    if not cmd_stripped:
        raise ToolCallBlocked("run_command: empty command")

    first_token = _extract_first_token(cmd_stripped)

    # Layer 1: First-token blocklist
    if first_token in BLOCKED_FIRST_TOKENS:
        raise ToolCallBlocked(
            f"Blocked command: '{first_token}' is not permitted"
        )

    # Layer 2: Recursive rm
    if _RM_RECURSIVE_PATTERN.search(cmd_stripped):
        raise ToolCallBlocked(
            "Recursive rm (rm -r / rm -rf) is not permitted."
        )

    # Layer 3: Shell injection
    for pattern, description in _SHELL_INJECTION_PATTERNS:
        if pattern.search(cmd_stripped):
            raise ToolCallBlocked(
                f"Shell injection detected: {description}. "
                "Use separate tool calls instead of chaining."
            )

    # Layer 4: Blocked-anywhere tokens
    cmd_lower = cmd_stripped.lower()
    for token in BLOCKED_ANYWHERE_TOKENS:
        if re.search(rf'\b{token}\b', cmd_lower):
            raise ToolCallBlocked(
                f"Command contains blocked operation: '{token}'."
            )

    # Layer 5: Command argument path containment
    # Prevents using allowed commands (cat, grep, etc.) to access
    # files outside the project root.
    _validate_command_arguments(cmd_stripped, project_root)

    # Layer 6: Git command validation
    if first_token == "git":
        _validate_git_command(cmd_stripped, allowed_branch)
        return  # Git commands don't need further allowlist checks

    # Layer 7: npm / npx scope validation
    # Only reachable if "node" runtime is active (npm/npx are node tools).
    node_tokens = RUNTIME_COMMAND_TOKENS.get("node", frozenset())
    if first_token == "npm" and "npm" in allowed_runtime_tokens:
        _validate_npm_command(cmd_stripped, allowed_npm_scripts)
        return
    if first_token == "npx" and "npx" in allowed_runtime_tokens:
        _validate_npx_command(cmd_stripped, allowed_npx_packages)
        return

    # Layer 8: Runtime command validation
    if first_token in allowed_runtime_tokens:
        return  # Allowed runtime command

    # Layer 9: Base command allowlist (filesystem utilities)
    allowed = any(
        cmd_stripped.startswith(prefix) or cmd_stripped == prefix.strip()
        for prefix in ALLOWED_BASE_COMMANDS
    )
    if allowed:
        return

    # Nothing matched — block with redirect hint
    _FILE_READ_CMDS = frozenset({
        "cat", "sed", "head", "tail", "less", "more", "awk",
        "grep", "python", "python3", "node",
    })
    hint = ""
    if first_token in _FILE_READ_CMDS:
        hint = " Use the read_file tool to read files instead."

    raise ToolCallBlocked(
        f"Command '{cmd_stripped[:80]}' is not permitted. "
        f"First token '{first_token}' is not in any allowlist.{hint}"
    )


# ── Sub-validators ───────────────────────────────────────────────────────────


def _validate_git_command(command: str, allowed_branch: str) -> None:
    """Validate git commands: subcommand allowlist + branch protection."""
    parts = command.strip().split()
    if len(parts) < 2:
        raise ToolCallBlocked("git command requires a subcommand")

    subcommand = parts[1].lower()

    # Check explicit blocklist first (better error messages)
    if subcommand in BLOCKED_GIT_SUBCOMMANDS:
        raise ToolCallBlocked(
            f"git {subcommand} is not permitted: "
            f"{BLOCKED_GIT_SUBCOMMANDS[subcommand]}"
        )

    # Check allowlist
    if subcommand not in ALLOWED_GIT_SUBCOMMANDS:
        raise ToolCallBlocked(
            f"git {subcommand} is not in the allowed subcommands: "
            f"{', '.join(sorted(ALLOWED_GIT_SUBCOMMANDS))}"
        )

    # Branch protection: 'git branch' (listing) is fine,
    # but 'git branch -d/-D' (deleting) is not.
    if subcommand == "branch":
        for flag in parts[2:]:
            if flag.startswith("-") and ("d" in flag.lower() or "m" in flag.lower()):
                raise ToolCallBlocked(
                    "git branch deletion/rename is not permitted."
                )

    # Validate commit is on the right branch (informational check —
    # the orchestrator already set up the branch, but this catches
    # if something went wrong)
    if subcommand == "commit" and allowed_branch:
        logger.debug(
            "EG1: git commit on expected branch '%s'", allowed_branch
        )


def _validate_npm_command(command: str, allowed_scripts: frozenset[str]) -> None:
    """Validate npm commands against project scope.

    Allowed:
        npm install  (no args — uses existing package.json)
        npm ci       (lockfile install)
        npm run <script>  where <script> is in package.json
        npm test     (shorthand for npm run test)

    Blocked:
        npm install <package>  (adding deps is a spec decision)
        npm run <unknown>      (script not in package.json)
    """
    parts = command.strip().split()
    if len(parts) < 2:
        raise ToolCallBlocked("npm requires a subcommand")

    sub = parts[1].lower()

    # npm install / npm ci (no additional package args)
    if sub in ("install", "i", "ci"):
        # Check if there are non-flag arguments (package names)
        non_flag_args = [p for p in parts[2:] if not p.startswith("-")]
        if non_flag_args:
            raise ToolCallBlocked(
                f"npm install with specific packages is not permitted: "
                f"'{' '.join(non_flag_args)}'. The agent must use the "
                f"existing package.json. Adding dependencies is a spec "
                f"decision, not a runtime decision."
            )
        return

    # npm test (shorthand for npm run test)
    if sub == "test" or sub == "t":
        return

    # npm run <script> — validate against package.json scripts
    if sub == "run" or sub == "run-script":
        if len(parts) < 3:
            raise ToolCallBlocked("npm run requires a script name")
        script_name = parts[2]
        if allowed_scripts and script_name not in allowed_scripts:
            raise ToolCallBlocked(
                f"npm run '{script_name}' not found in package.json scripts. "
                f"Allowed: {', '.join(sorted(allowed_scripts))}"
            )
        return

    # npm uninstall, npm publish, etc. — not permitted
    raise ToolCallBlocked(
        f"npm {sub} is not permitted. Allowed: install, ci, test, "
        f"run <script>"
    )


def _validate_npx_command(
    command: str, allowed_packages: frozenset[str]
) -> None:
    """Validate npx commands against known project packages.

    npx can fetch and execute arbitrary packages from the registry.
    Only packages from the project's devDependencies are permitted.

    If no package.json exists (allowed_packages is empty), all npx
    is blocked — there's no way to know what's legitimate.
    """
    parts = command.strip().split()
    if len(parts) < 2:
        raise ToolCallBlocked("npx requires a package/command name")

    # Skip flags to find the package name
    package = ""
    for part in parts[1:]:
        if part.startswith("-"):
            continue
        package = part.lower()
        break

    if not package:
        raise ToolCallBlocked("npx: could not determine package name")

    if not allowed_packages:
        raise ToolCallBlocked(
            "npx is blocked: no package.json found or no "
            "devDependencies to derive an allowlist from."
        )

    if package not in allowed_packages:
        raise ToolCallBlocked(
            f"npx '{package}' is not in project devDependencies. "
            f"Allowed: {', '.join(sorted(list(allowed_packages)[:10]))}"
            f"{'...' if len(allowed_packages) > 10 else ''}"
        )


# ── Executor ─────────────────────────────────────────────────────────────────


class BuildAgentExecutor:
    """ToolExecutor implementation for the build agent.

    Validates every tool call against path and command restrictions,
    then executes within the project sandbox.

    Supported tools:
        write_file(path, content)  — Write content to a file
        read_file(path)            — Read a file's contents
        run_command(command)        — Execute a shell command

    Constructor derives npm/npx allowlists from package.json and
    builds runtime token allowlists from the specified runtimes.
    """

    def __init__(
        self,
        project_root: Path,
        allowed_branch: str = "",
        allowed_runtimes: set[str] | None = None,
        command_timeout: int = 60,
        protected_paths: set[str | Path] | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.allowed_branch = allowed_branch
        self.command_timeout = command_timeout
        self._written_files: set[str] = set()

        # Track blocked command patterns for cross-feature learning.
        # After each feature, the build loop reads these and injects
        # them into the next feature's system prompt so the agent
        # doesn't repeat the same mistakes.
        self.blocked_patterns: list[str] = []

        # Paths the agent cannot write to (e.g. test files).
        # Resolved at construction so matching is exact.
        if protected_paths:
            self._protected_paths: frozenset[str] = frozenset(
                str((project_root / p).resolve()) for p in protected_paths
            )
            logger.info("EG1: %d protected path(s)", len(self._protected_paths))
        else:
            self._protected_paths = frozenset()

        # Derive runtimes: explicit > auto-detected
        self._explicit_runtimes = allowed_runtimes
        self._refresh_runtimes()

        logger.info(
            "EG1 init: project=%s, branch=%s, runtimes=%s, "
            "npm_scripts=%d, npx_packages=%d",
            project_root.name,
            allowed_branch or "(none)",
            ",".join(sorted(self._current_runtimes)) or "(none)",
            len(self._allowed_npm_scripts),
            len(self._allowed_npx_packages),
        )

    # ── Runtime marker files that trigger re-detection (P8) ────────
    # When write_file creates one of these, runtime allowlists are
    # re-derived. This handles project bootstrapping — the agent can
    # create package.json and then use npm commands in the same session.
    _RUNTIME_MARKERS: frozenset[str] = frozenset({
        "package.json", "tsconfig.json", ".nvmrc",
        "pyproject.toml", "requirements.txt", "setup.py", "Pipfile",
        "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
        "Gemfile", "composer.json", "Package.swift",
    })

    def _refresh_runtimes(self) -> None:
        """Re-derive runtime allowlists from current disk state.

        Called at construction and after write_file creates a marker file.
        """
        if self._explicit_runtimes is not None:
            runtimes = self._explicit_runtimes
        else:
            runtimes = detect_project_runtimes(self.project_root)

        self._current_runtimes = runtimes
        self._allowed_runtime_tokens = frozenset().union(
            *(RUNTIME_COMMAND_TOKENS.get(r, frozenset()) for r in runtimes)
        )

        pkg = _parse_package_json(self.project_root)
        self._allowed_npm_scripts = frozenset(pkg["scripts"])
        self._allowed_npx_packages = frozenset(
            pkg["dev_deps"] | pkg["deps"] | self._allowed_runtime_tokens
        )

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Validate and execute a tool call.

        Satisfies the ToolExecutor protocol from local_agent.py.
        Returns a JSON string result on success.
        Raises ToolCallBlocked on validation failure, recording the
        pattern for cross-feature learning.
        """
        # Translate common model mistakes before dispatch (P8).
        # Models understand intent but can't map to the 3-tool schema.
        # Meet them where they are instead of burning turns on rejections.
        name, arguments = self._translate_tool_call(name, arguments)

        try:
            return self._dispatch(name, arguments)
        except ToolCallBlocked as exc:
            # Record the rejection pattern for prompt injection
            pattern = f"{name}: {str(exc)[:120]}"
            if pattern not in self.blocked_patterns:
                self.blocked_patterns.append(pattern)
            raise

    def _translate_tool_call(
        self, name: str, arguments: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Translate common model mistakes into correct tool calls.

        Models understand intent but can't map to the 3-tool schema.
        Instead of blocking and hoping they learn (they don't — empirically
        confirmed across GPT-OSS-120B, Qwen3-Coder-Next, GLM-4.7), translate
        their intent into the correct tool call. EG1 still validates the
        translated call — security is unchanged.

        Translation rules:
        - Unknown tool names that imply file reading → read_file
        - Unknown tool names that imply directory listing → run_command(ls)
        - read_file with 'command' arg instead of 'path' → extract path
        - run_command with file-reading commands (sed, cat, head, etc.) → read_file
        - run_command with python -c reading files → read_file
        """
        # ── Unknown tool names → map to known tools ──────────────
        _READ_ALIASES = frozenset({
            "cat", "view", "view_file", "get_file", "read",
            "file_read", "open_file", "show_file",
        })
        _DIR_ALIASES = frozenset({
            "listdir", "list_dir", "list_directory", "ls", "dir",
            "list_files", "get_directory", "browse",
        })

        if name in _READ_ALIASES:
            path = arguments.get("path", arguments.get("file", ""))
            logger.info("EG1 translate: %s → read_file(%s)", name, path)
            return "read_file", {"path": path}

        if name in _DIR_ALIASES:
            path = arguments.get("path", arguments.get("directory", "."))
            logger.info("EG1 translate: %s → run_command(ls %s)", name, path)
            return "run_command", {"command": f"ls -la {path}"}

        # ── read_file with wrong argument names ──────────────────
        if name == "read_file" and "path" not in arguments:
            # Model passed command="cat file" or file="path"
            cmd = arguments.get("command", "")
            file_arg = arguments.get("file", arguments.get("filename", ""))
            if cmd:
                # Extract path from "cat /path/to/file" style
                parts = cmd.strip().split()
                path = parts[-1] if parts else ""
                logger.info("EG1 translate: read_file(command=%s) → read_file(path=%s)", cmd[:60], path)
                return "read_file", {"path": path}
            if file_arg:
                logger.info("EG1 translate: read_file(file=%s) → read_file(path=%s)", file_arg, file_arg)
                return "read_file", {"path": file_arg}

        # ── run_command with file-reading intent → read_file ─────
        if name == "run_command":
            cmd = arguments.get("command", "").strip()
            # Match: cat <file>, head <file>, tail <file>, sed -n '...' <file>
            _READ_CMD_PATTERNS = [
                (r'^cat\s+(.+)$',),
                (r'^head\s+(?:-\d+\s+)?(.+)$',),
                (r'^tail\s+(?:-\d+\s+)?(.+)$',),
                (r"^sed\s+-n\s+'[^']+'\s+(.+)$",),
                (r'^less\s+(.+)$',),
                (r'^more\s+(.+)$',),
            ]
            for patterns in _READ_CMD_PATTERNS:
                for pattern in patterns:
                    m = re.match(pattern, cmd)
                    if m:
                        path = m.group(1).strip().strip("'\"")
                        # Strip pipe/redirect suffixes: "file | head" → "file"
                        path = re.split(r'\s*[|><;]', path)[0].strip()
                        if path:
                            logger.info("EG1 translate: run_command(%s) → read_file(%s)", cmd[:60], path)
                            return "read_file", {"path": path}

            # Match: python -c "...open('file')..." or python -c "...read_text()..."
            py_match = re.match(r'^python[3]?\s+-c\s+["\'](.+)["\']$', cmd, re.DOTALL)
            if py_match:
                py_code = py_match.group(1)
                # Try to extract file path from open() or Path() calls
                file_match = re.search(r"open\(['\"]([^'\"]+)['\"]\)", py_code)
                if not file_match:
                    file_match = re.search(r"Path\(['\"]([^'\"]+)['\"]\)", py_code)
                if file_match:
                    path = file_match.group(1)
                    logger.info("EG1 translate: python -c → read_file(%s)", path)
                    return "read_file", {"path": path}

            # Match: ls <path> with optional error suppression
            # Models write: ls -la /path 2>/dev/null || echo "No dir"
            # Strip the error handling, keep the ls
            ls_match = re.match(r'^(ls\s+(?:-[a-zA-Z]+\s+)?\S+)', cmd)
            if ls_match:
                clean_ls = ls_match.group(1).strip()
                if clean_ls != cmd:
                    logger.info(
                        "EG1 translate: cleaned ls command: %s → %s",
                        cmd[:60], clean_ls,
                    )
                return "run_command", {"command": clean_ls}

        return name, arguments

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        """Inner dispatch — separated so execute() can catch blocks."""
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

        if not isinstance(path_str, str):
            raise ToolCallBlocked("write_file: 'path' must be a string")
        if not path_str:
            raise ToolCallBlocked("write_file: 'path' is required")
        if not isinstance(content, str):
            raise ToolCallBlocked("write_file: 'content' must be a string")

        _validate_path(path_str, self.project_root)
        full_path = (self.project_root / path_str).resolve()
        if not _is_path_within_project(path_str, self.project_root):
            raise ToolCallBlocked(
                f"write_file: path '{full_path}' escapes project root"
            )

        if str(full_path) in self._protected_paths:
            raise ToolCallBlocked(
                f"write_file: '{path_str}' is a protected file "
                f"(e.g. test file). The agent cannot modify it."
            )

        try:
            os.makedirs(full_path.parent, exist_ok=True)
            full_path.write_text(content)
            self._written_files.add(str(full_path))
            logger.debug("EG1 write_file: %s (%d bytes)", path_str, len(content))

            # Re-detect runtimes if a marker file was created/modified (P8)
            basename = Path(path_str).name
            if basename in self._RUNTIME_MARKERS:
                old_runtimes = self._current_runtimes.copy()
                self._refresh_runtimes()
                new_runtimes = self._current_runtimes - old_runtimes
                if new_runtimes:
                    logger.info(
                        "EG1: runtime re-detected after %s: +%s",
                        basename, ",".join(sorted(new_runtimes)),
                    )

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
        if not isinstance(path_str, str):
            raise ToolCallBlocked("read_file: 'path' must be a string")
        if not path_str:
            raise ToolCallBlocked("read_file: 'path' is required")

        _validate_path(path_str, self.project_root)
        full_path = (self.project_root / path_str).resolve()
        if not _is_path_within_project(path_str, self.project_root):
            raise ToolCallBlocked(
                f"read_file: path '{full_path}' escapes project root"
            )

        try:
            content = full_path.read_text()
            # Return full content up to 50KB. Context management is handled
            # by _trim_old_tool_results in local_agent.py — old results get
            # compressed so accumulated history doesn't fill the window.
            # Capping individual reads causes re-reads (model sees truncated
            # and loops back), making the problem worse.
            max_chars = 50000
            truncated = len(content) > max_chars
            logger.debug("EG1 read_file: %s (%d bytes)", path_str, len(content))
            return json.dumps({
                "content": content[:max_chars],
                "path": path_str,
                "size": len(content),
                "truncated": truncated,
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

        # Strip redundant cd <project_dir> && prefix (P8: generalizable).
        command = self._strip_cd_prefix(command)

        # Strip || fallback chains. Models write "cmd1 || cmd2" as error
        # handling. Run the primary command only — if it fails, the model
        # sees the error and can call the fallback separately.
        command = self._strip_fallback_chain(command)

        # Handle git add && git commit chains (P8: standard dev pattern).
        # Models write "git add -A && git commit -m '...'" because that's
        # how developers do it. Split and run sequentially.
        git_chain = self._split_git_chain(command)
        if git_chain:
            return self._exec_git_chain(git_chain)

        # Write-then-exec detection (before general validation)
        self._check_write_then_exec(command)

        # Full command validation
        _validate_command_layers(
            command,
            self._allowed_runtime_tokens,
            self._allowed_npm_scripts,
            self._allowed_npx_packages,
            self.allowed_branch,
            self.project_root,
        )

        try:
            result = subprocess.run(
                command, shell=True,
                capture_output=True, text=True,
                timeout=self.command_timeout,
                cwd=str(self.project_root),
            )
            logger.debug("EG1 run_command: %s (rc=%d)", command[:80], result.returncode)
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

    def _strip_cd_prefix(self, command: str) -> str:
        """Strip redundant cd <path> && prefix from commands.

        Models habitually write 'cd /project && actual_command'. Since
        run_command already executes with cwd=project_root, the cd is
        a no-op. Strip it so the actual command passes validation.

        Only strips if the cd target resolves to project_root or is
        '.' or a relative path within the project. cd to paths outside
        the project are left intact (will be caught by other checks).
        """
        # Match: cd <path> && <rest>  (with optional whitespace)
        cd_match = re.match(
            r'^cd\s+(\S+)\s*&&\s*(.+)$', command.strip(), re.DOTALL,
        )
        if not cd_match:
            return command

        cd_target = cd_match.group(1).strip("'\"")
        rest = cd_match.group(2).strip()

        # Check if cd target is the project root or within it
        try:
            target_path = Path(cd_target).resolve()
        except (OSError, ValueError):
            return command

        project_str = str(self.project_root)
        if (
            cd_target == "."
            or str(target_path) == project_str
            or str(target_path).startswith(project_str + "/")
        ):
            logger.debug(
                "EG1: stripped redundant 'cd %s &&' prefix", cd_target,
            )
            return rest

        return command

    def _strip_fallback_chain(self, command: str) -> str:
        """Strip || fallback from commands.

        Models write 'cmd1 || cmd2' as error handling — try the primary
        command, fall back if it fails. We run the primary command only.
        If it fails, the model sees the error and can run the fallback
        as a separate tool call.

        Also strips '2>&1' and '2>/dev/null' stderr redirects since
        subprocess.run captures stderr separately.
        """
        cmd = command.strip()
        # Strip stderr redirects first
        cmd = re.sub(r'\s*2>[>&]?[/\w]*', '', cmd).strip()
        # Strip || fallback
        if '||' in cmd:
            primary = cmd.split('||')[0].strip()
            if primary:
                logger.debug("EG1: stripped fallback chain, keeping: %s", primary[:60])
                return primary
        return cmd

    def _split_git_chain(self, command: str) -> list[str] | None:
        """Split chained git commands into individual commands.

        Recognizes patterns like:
            git add -A && git commit -m "message"
            git add . && git commit -m "message"
            git add file.ts && git commit -m "message"

        Returns list of individual git commands, or None if not a git chain.
        """
        cmd = command.strip()
        if not cmd.startswith("git "):
            return None
        # Split on && and check each part is a git command
        parts = [p.strip() for p in cmd.split("&&")]
        if len(parts) < 2:
            return None
        if all(p.startswith("git ") for p in parts):
            return parts
        return None

    def _exec_git_chain(self, commands: list[str]) -> str:
        """Execute a chain of git commands sequentially.

        Each command is validated individually through the normal
        command validation pipeline.
        """
        results = []
        for cmd in commands:
            # Validate each command
            _validate_command_layers(
                cmd,
                self._allowed_runtime_tokens,
                self._allowed_npm_scripts,
                self._allowed_npx_packages,
                self.allowed_branch,
                self.project_root,
            )
            try:
                result = subprocess.run(
                    cmd, shell=True,
                    capture_output=True, text=True,
                    timeout=self.command_timeout,
                    cwd=str(self.project_root),
                )
                results.append({
                    "command": cmd,
                    "stdout": result.stdout[:2000],
                    "stderr": result.stderr[:1000],
                    "returncode": result.returncode,
                })
                if result.returncode != 0:
                    logger.info("Git chain stopped at '%s' (rc=%d)", cmd[:60], result.returncode)
                    break
            except subprocess.TimeoutExpired:
                results.append({"command": cmd, "error": "timeout", "returncode": -1})
                break
        logger.info("EG1: executed git chain (%d commands)", len(results))
        return json.dumps(results)

    def _check_write_then_exec(self, command: str) -> None:
        """Detect and block execution of agent-written scripts.

        If the agent wrote a file with an executable extension during
        this session and now tries to reference it in a command, block
        it. Also blocks npm run after agent modified package.json.
        """
        if not self._written_files:
            return

        # Git commands reference files but don't execute them.
        cmd_stripped = command.strip()
        if cmd_stripped.startswith("git "):
            return

        # Test runners load files in a sandbox, they don't execute them
        # as scripts. The threat model is "agent writes malicious script
        # and runs it" not "agent runs tests against code it wrote."
        _TEST_RUNNERS = frozenset({
            "vitest", "jest", "pytest", "mocha", "ava", "tap",
            "npx vitest", "npx jest", "npx mocha",
            "npm test", "npm run test",
        })
        for runner in _TEST_RUNNERS:
            if cmd_stripped.startswith(runner):
                return

        cmd_parts = cmd_stripped.split()
        for part in cmd_parts:
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

        # npm run after package.json modification
        pkg_json = str(self.project_root / "package.json")
        if pkg_json in self._written_files:
            if command.strip().startswith("npm run"):
                raise ToolCallBlocked(
                    "Agent modified package.json and is now running "
                    "'npm run' — the scripts section may contain "
                    "arbitrary commands. Commit and review first."
                )
