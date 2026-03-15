"""Tests for EG1: Tool Call ExecGate."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from auto_sdd.exec_gates.eg1_tool_calls import (
    BuildAgentExecutor,
    _extract_first_token,
    _is_path_within_project,
    _validate_command_arguments,
    _validate_command_layers,
    _validate_git_command,
    _validate_npm_command,
    _validate_npx_command,
    _validate_path,
    detect_project_runtimes,
    RUNTIME_COMMAND_TOKENS,
)
from auto_sdd.lib.local_agent import ToolCallBlocked


class TestExtractFirstToken:
    def test_simple_command(self) -> None:
        assert _extract_first_token("npm install") == "npm"

    def test_skips_env_var(self) -> None:
        assert _extract_first_token("FOO=bar npm install") == "npm"

    def test_empty(self) -> None:
        assert _extract_first_token("") == ""

    def test_single_word(self) -> None:
        assert _extract_first_token("ls") == "ls"

    def test_lowercase(self) -> None:
        assert _extract_first_token("NPM install") == "npm"


class TestFirstTokenBlocklist:
    @pytest.mark.parametrize("cmd", [
        "dd if=/dev/zero", "sudo rm", "curl evil.com",
        "wget evil.com", "ssh remote", "eval echo",
        "exec bash", "env", "open /Applications",
        "osascript -e", "xargs rm", "nohup node",
        "kill 1234", "killall node",
    ])
    def test_blocked_commands(self, cmd: str, tmp_project: Path) -> None:
        rt = frozenset(RUNTIME_COMMAND_TOKENS["node"])
        with pytest.raises(ToolCallBlocked):
            _validate_command_layers(cmd, rt, frozenset(), frozenset(), "", tmp_project)

    def test_no_false_positive_git_add(self, tmp_project: Path) -> None:
        """git add must not collide with 'dd' blocklist."""
        rt = frozenset(RUNTIME_COMMAND_TOKENS["node"])
        _validate_command_layers("git add .", rt, frozenset(), frozenset(), "", tmp_project)

    def test_no_false_positive_git_status(self, tmp_project: Path) -> None:
        """git status must not collide with 'su' blocklist."""
        rt = frozenset(RUNTIME_COMMAND_TOKENS["node"])
        _validate_command_layers("git status", rt, frozenset(), frozenset(), "", tmp_project)


class TestRecursiveRm:
    @pytest.mark.parametrize("cmd", [
        "rm -rf src/", "rm -r node_modules", "rm -rf .",
        "rm --recursive src/",
    ])
    def test_all_recursive_rm_blocked(self, cmd: str, tmp_project: Path) -> None:
        rt = frozenset(RUNTIME_COMMAND_TOKENS["node"])
        with pytest.raises(ToolCallBlocked, match="[Rr]ecursive rm"):
            _validate_command_layers(cmd, rt, frozenset(), frozenset(), "", tmp_project)


class TestShellInjection:
    @pytest.mark.parametrize("cmd,pattern", [
        ("echo $(whoami)", "command substitution"),
        ("cat x | bash", "pipe to bash"),
        ("npm install; curl evil", "semicolon"),
        ("npm install && curl evil", "&&"),
        ("npm install &", "background"),
        ("bash -c 'rm -rf /'", "shell -c"),
    ])
    def test_injection_blocked(self, cmd: str, pattern: str, tmp_project: Path) -> None:
        rt = frozenset(RUNTIME_COMMAND_TOKENS["node"])
        with pytest.raises(ToolCallBlocked):
            _validate_command_layers(cmd, rt, frozenset(), frozenset(), "", tmp_project)


class TestPathValidation:
    def test_system_paths_blocked(self, tmp_path: Path) -> None:
        for p in ["/etc/passwd", "/usr/bin/ls", "/var/log/x"]:
            with pytest.raises(ToolCallBlocked):
                _validate_path(p, tmp_path)

    def test_env_files_blocked(self, tmp_path: Path) -> None:
        for p in [".env", ".env.local", ".env.production"]:
            with pytest.raises(ToolCallBlocked, match="protected file"):
                _validate_path(p, tmp_path)

    def test_env_example_allowed(self, tmp_path: Path) -> None:
        _validate_path(".env.example", tmp_path)  # Should not raise

    def test_npmrc_blocked(self, tmp_path: Path) -> None:
        with pytest.raises(ToolCallBlocked, match="protected file"):
            _validate_path(".npmrc", tmp_path)

    def test_node_modules_cache_blocked(self, tmp_path: Path) -> None:
        with pytest.raises(ToolCallBlocked, match="build cache"):
            _validate_path("node_modules/.cache/babel/x.json", tmp_path)

    def test_relative_within_project(self, tmp_path: Path) -> None:
        _validate_path("src/index.ts", tmp_path)  # Should not raise

    def test_parent_traversal_blocked(self, tmp_path: Path) -> None:
        with pytest.raises(ToolCallBlocked):
            _validate_path("../../etc/passwd", tmp_path)

    def test_is_path_within_project(self, tmp_path: Path) -> None:
        assert _is_path_within_project("src/x.ts", tmp_path) is True
        assert _is_path_within_project("../../x", tmp_path) is False


class TestCommandArgumentContainment:
    def test_cat_local_file_allowed(self, tmp_path: Path) -> None:
        _validate_command_arguments("cat src/index.ts", tmp_path)

    def test_cat_outside_project_blocked(self, tmp_path: Path) -> None:
        with pytest.raises(ToolCallBlocked, match="outside project root"):
            _validate_command_arguments("cat /etc/passwd", tmp_path)

    def test_cat_home_dir_blocked(self, tmp_path: Path) -> None:
        with pytest.raises(ToolCallBlocked, match="outside project root"):
            _validate_command_arguments("cat ~/other-project/secret", tmp_path)

    def test_grep_outside_blocked(self, tmp_path: Path) -> None:
        with pytest.raises(ToolCallBlocked):
            _validate_command_arguments("grep -r password /etc/", tmp_path)

    def test_non_path_commands_pass_through(self, tmp_path: Path) -> None:
        _validate_command_arguments("npm install", tmp_path)
        _validate_command_arguments("git status", tmp_path)


class TestGitValidation:
    @pytest.mark.parametrize("cmd", [
        "git add .", "git commit -m 'x'", "git status",
        "git diff", "git log", "git show HEAD",
    ])
    def test_allowed_subcommands(self, cmd: str) -> None:
        _validate_git_command(cmd, "feat/x")

    @pytest.mark.parametrize("cmd,expected_msg", [
        ("git push", "Pushes are managed"),
        ("git merge main", "Merges are managed"),
        ("git rebase main", "Rebases are managed"),
        ("git reset --hard", "Resets are managed"),
        ("git checkout main", "Branch switching"),
        ("git stash", "Stashing is managed"),
        ("git clean -fd", "git clean is managed"),
    ])
    def test_blocked_subcommands(self, cmd: str, expected_msg: str) -> None:
        with pytest.raises(ToolCallBlocked, match=expected_msg):
            _validate_git_command(cmd, "feat/x")

    def test_branch_delete_blocked(self) -> None:
        with pytest.raises(ToolCallBlocked, match="deletion"):
            _validate_git_command("git branch -d old-branch", "feat/x")


class TestNpmValidation:
    scripts = frozenset({"build", "test", "dev"})

    def test_install_no_args(self) -> None:
        _validate_npm_command("npm install", self.scripts)

    def test_ci(self) -> None:
        _validate_npm_command("npm ci", self.scripts)

    def test_test(self) -> None:
        _validate_npm_command("npm test", self.scripts)

    def test_run_known_script(self) -> None:
        _validate_npm_command("npm run build", self.scripts)

    def test_install_package_blocked(self) -> None:
        with pytest.raises(ToolCallBlocked, match="specific packages"):
            _validate_npm_command("npm install lodash", self.scripts)

    def test_run_unknown_script_blocked(self) -> None:
        with pytest.raises(ToolCallBlocked, match="not found"):
            _validate_npm_command("npm run deploy", self.scripts)

    def test_publish_blocked(self) -> None:
        with pytest.raises(ToolCallBlocked):
            _validate_npm_command("npm publish", self.scripts)


class TestNpxValidation:
    def test_known_package(self) -> None:
        _validate_npx_command("npx eslint .", frozenset({"eslint", "tsc"}))

    def test_unknown_package_blocked(self) -> None:
        with pytest.raises(ToolCallBlocked, match="not in project"):
            _validate_npx_command("npx evil-pkg", frozenset({"eslint"}))

    def test_empty_deps_blocked(self) -> None:
        with pytest.raises(ToolCallBlocked, match="no package.json"):
            _validate_npx_command("npx anything", frozenset())


class TestRuntimeDetection:
    def test_detects_node(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}")
        assert "node" in detect_project_runtimes(tmp_path)

    def test_detects_python(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]")
        assert "python" in detect_project_runtimes(tmp_path)

    def test_detects_rust(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text("[package]")
        assert "rust" in detect_project_runtimes(tmp_path)

    def test_empty_project(self, tmp_path: Path) -> None:
        assert len(detect_project_runtimes(tmp_path)) == 0


class TestBuildAgentExecutor:
    def test_write_and_read(self, tmp_project: Path) -> None:
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = json.loads(ex.execute("write_file", {
            "path": "test.txt", "content": "hello",
        }))
        assert result["status"] == "success"

        result = json.loads(ex.execute("read_file", {"path": "test.txt"}))
        assert result["content"] == "hello"

    def test_write_outside_project_blocked(self, tmp_project: Path) -> None:
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        with pytest.raises(ToolCallBlocked):
            ex.execute("write_file", {"path": "/etc/passwd", "content": "x"})

    def test_write_env_blocked(self, tmp_project: Path) -> None:
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        with pytest.raises(ToolCallBlocked, match="protected file"):
            ex.execute("write_file", {"path": ".env", "content": "SECRET=x"})

    def test_unknown_tool_blocked(self, tmp_project: Path) -> None:
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        with pytest.raises(ToolCallBlocked, match="Unknown tool"):
            ex.execute("delete_file", {"path": "x"})

    def test_malformed_args_blocked(self, tmp_project: Path) -> None:
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        with pytest.raises(ToolCallBlocked, match="malformed"):
            ex.execute("write_file", {"_parse_error": "bad json", "_raw": "{"})

    def test_write_then_exec_blocked(self, tmp_project: Path) -> None:
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        ex.execute("write_file", {"path": "setup.sh", "content": "#!/bin/bash\necho hi"})
        with pytest.raises(ToolCallBlocked, match="[Ww]rite-then-exec"):
            ex.execute("run_command", {"command": "bash setup.sh"})

    def test_python_blocked_in_node_project(self, tmp_project: Path) -> None:
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        with pytest.raises(ToolCallBlocked):
            ex.execute("run_command", {"command": "python3 script.py"})

    def test_python_allowed_in_python_project(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]")
        ex = BuildAgentExecutor(tmp_path, allowed_runtimes={"python"})
        # python3 --version should work (no file needed)
        result = json.loads(ex.execute("run_command", {"command": "python3 --version"}))
        assert result["returncode"] == 0

    def test_git_push_blocked(self, tmp_project: Path) -> None:
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        with pytest.raises(ToolCallBlocked, match="[Pp]ushes"):
            ex.execute("run_command", {"command": "git push"})

    def test_npm_install_package_blocked(self, tmp_project: Path) -> None:
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        with pytest.raises(ToolCallBlocked, match="specific packages"):
            ex.execute("run_command", {"command": "npm install lodash"})

    def test_protected_path_write_blocked(self, tmp_project: Path) -> None:
        test_file = "tests/test_login.spec.ts"
        (tmp_project / "tests").mkdir()
        (tmp_project / test_file).write_text("original")
        ex = BuildAgentExecutor(
            tmp_project, allowed_runtimes={"node"},
            protected_paths={test_file},
        )
        with pytest.raises(ToolCallBlocked, match="protected file"):
            ex.execute("write_file", {"path": test_file, "content": "tampered"})
        # Verify file wasn't modified
        assert (tmp_project / test_file).read_text() == "original"

    def test_non_protected_path_write_allowed(self, tmp_project: Path) -> None:
        ex = BuildAgentExecutor(
            tmp_project, allowed_runtimes={"node"},
            protected_paths={"tests/test_login.spec.ts"},
        )
        ex.execute("write_file", {"path": "src/app.ts", "content": "code"})
        assert (tmp_project / "src/app.ts").read_text() == "code"


# ── Runtime re-detection (P8: fixes must generalize) ─────────────────────────


class TestRuntimeRedetection:
    """EG1 re-derives runtimes when write_file creates a marker file."""

    def test_npm_blocked_without_package_json(self, tmp_path: Path) -> None:
        """Project with no marker files blocks npm."""
        ex = BuildAgentExecutor(tmp_path)
        with pytest.raises(ToolCallBlocked):
            ex.execute("run_command", {"command": "npm install"})

    def test_npm_allowed_after_writing_package_json(self, tmp_path: Path) -> None:
        """Writing package.json triggers re-detection, unblocking npm."""
        ex = BuildAgentExecutor(tmp_path)
        # npm blocked before
        with pytest.raises(ToolCallBlocked):
            ex.execute("run_command", {"command": "npm install"})
        # Write package.json
        ex.execute("write_file", {
            "path": "package.json",
            "content": json.dumps({"scripts": {"build": "tsc"}, "dependencies": {}}),
        })
        # npm install (no args) allowed after — EG1 permits it
        # (note: npm run is separately blocked after write_file per script injection guard)
        result = ex.execute("run_command", {"command": "npm install"})
        assert isinstance(result, str)  # got a response, not blocked

    def test_python_allowed_after_writing_pyproject(self, tmp_path: Path) -> None:
        """Writing pyproject.toml triggers re-detection for python runtime."""
        ex = BuildAgentExecutor(tmp_path)
        # python blocked before
        with pytest.raises(ToolCallBlocked):
            ex.execute("run_command", {"command": "python3 --version"})
        # Write pyproject.toml
        ex.execute("write_file", {
            "path": "pyproject.toml",
            "content": "[project]\nname = 'test'\n",
        })
        # python allowed after
        result = ex.execute("run_command", {"command": "python3 --version"})
        assert isinstance(result, str)

    def test_non_marker_file_does_not_retrigger(self, tmp_path: Path) -> None:
        """Writing a regular file doesn't change runtimes."""
        ex = BuildAgentExecutor(tmp_path)
        ex.execute("write_file", {"path": "README.md", "content": "# readme"})
        # Still no runtimes
        with pytest.raises(ToolCallBlocked):
            ex.execute("run_command", {"command": "npm install"})


# ── cd prefix stripping (P8: generalizable) ──────────────────────────────────


class TestCdPrefixStripping:
    """EG1 strips redundant cd <project> && prefix from commands."""

    def test_cd_project_dir_stripped(self, tmp_project: Path) -> None:
        """cd <project_root> && command → command runs without block."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("run_command", {
            "command": f"cd {tmp_project} && git status",
        })
        assert isinstance(result, str)  # not blocked

    def test_cd_dot_stripped(self, tmp_project: Path) -> None:
        """cd . && command → command runs."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("run_command", {
            "command": "cd . && git status",
        })
        assert isinstance(result, str)

    def test_cd_subdir_stripped(self, tmp_project: Path) -> None:
        """cd <project>/src && command → stripped (within project)."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("run_command", {
            "command": f"cd {tmp_project}/src && git status",
        })
        assert isinstance(result, str)

    def test_cd_outside_project_not_stripped(self, tmp_project: Path) -> None:
        """cd /etc && command → NOT stripped, still blocked."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        with pytest.raises(ToolCallBlocked, match="command chaining"):
            ex.execute("run_command", {"command": "cd /etc && ls"})

    def test_no_cd_prefix_unchanged(self, tmp_project: Path) -> None:
        """Regular commands pass through unchanged."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("run_command", {"command": "git status"})
        assert isinstance(result, str)

    def test_real_chaining_still_blocked(self, tmp_project: Path) -> None:
        """Non-git chaining is still blocked."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        with pytest.raises(ToolCallBlocked, match="command chaining"):
            ex.execute("run_command", {
                "command": "echo hello && echo world",
            })


# ── Tool call translation (P8: meet models where they are) ───────────────────


class TestToolCallTranslation:
    """EG1 translates common model mistakes instead of blocking."""

    def test_listdir_translated_to_ls(self, tmp_project: Path) -> None:
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("listdir", {"path": "."})
        parsed = json.loads(result)
        assert "stdout" in parsed or "stderr" in parsed

    def test_list_dir_translated(self, tmp_project: Path) -> None:
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("list_dir", {"path": "."})
        parsed = json.loads(result)
        assert "stdout" in parsed or "stderr" in parsed

    def test_list_directory_translated(self, tmp_project: Path) -> None:
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("list_directory", {"path": "."})
        parsed = json.loads(result)
        assert "stdout" in parsed or "stderr" in parsed

    def test_sed_translated_to_read_file(self, tmp_project: Path) -> None:
        (tmp_project / "src" / "app.ts").write_text("const x = 1;\n")
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("run_command", {
            "command": "sed -n '1,200p' src/app.ts",
        })
        parsed = json.loads(result)
        assert "const x = 1" in parsed.get("content", "")

    def test_cat_translated_to_read_file(self, tmp_project: Path) -> None:
        (tmp_project / "src" / "app.ts").write_text("hello world\n")
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("run_command", {
            "command": "cat src/app.ts",
        })
        parsed = json.loads(result)
        assert "hello world" in parsed.get("content", "")

    def test_read_file_with_command_arg(self, tmp_project: Path) -> None:
        """Model passes command='cat file' to read_file instead of path."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("read_file", {
            "command": "cat src/index.ts",
        })
        parsed = json.loads(result)
        assert "content" in parsed

    def test_read_file_with_file_arg(self, tmp_project: Path) -> None:
        """Model passes file='path' instead of path='path'."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("read_file", {
            "file": "src/index.ts",
        })
        parsed = json.loads(result)
        assert "content" in parsed

    def test_ls_with_error_chaining_cleaned(self, tmp_project: Path) -> None:
        """ls -la path 2>/dev/null || echo 'No dir' → ls -la path."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("run_command", {
            "command": "ls -la src 2>/dev/null || echo 'No src'",
        })
        parsed = json.loads(result)
        assert "stdout" in parsed

    def test_python_file_read_translated(self, tmp_project: Path) -> None:
        """python -c with open() → read_file."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("run_command", {
            "command": "python -c \"import json; data=json.load(open('data/seed.json')); print(data)\"",
        })
        # Should translate to read_file("data/seed.json")
        # File may not exist but shouldn't be blocked by EG1
        assert isinstance(result, str)

    def test_real_write_file_not_translated(self, tmp_project: Path) -> None:
        """Normal write_file calls pass through unchanged."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("write_file", {
            "path": "test.txt", "content": "hello",
        })
        parsed = json.loads(result)
        assert parsed["status"] == "success"

    def test_real_run_command_not_translated(self, tmp_project: Path) -> None:
        """Normal git commands pass through unchanged."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("run_command", {"command": "git status"})
        parsed = json.loads(result)
        assert "stdout" in parsed


# ── Git chain handling ───────────────────────────────────────────────────────


class TestGitChain:
    """EG1 handles git add && git commit as a valid pattern."""

    def test_git_add_commit_chain(self, tmp_project: Path) -> None:
        """git add -A && git commit is executed, not blocked."""
        import subprocess as sp
        env = {**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t"}
        sp.run(["git", "init", "-b", "main"], cwd=str(tmp_project),
               capture_output=True, env=env)
        sp.run(["git", "add", "-A"], cwd=str(tmp_project),
               capture_output=True, env=env)
        sp.run(["git", "commit", "-m", "init", "--allow-empty"],
               cwd=str(tmp_project), capture_output=True, env=env)

        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("run_command", {
            "command": "git add -A && git commit -m 'test commit' --allow-empty",
        })
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["command"].startswith("git add")
        assert parsed[1]["command"].startswith("git commit")

    def test_non_git_chaining_still_blocked(self, tmp_project: Path) -> None:
        """Mixed git + non-git chaining is blocked."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        with pytest.raises(ToolCallBlocked):
            ex.execute("run_command", {
                "command": "git add -A && npm run build",
            })


# ── Write-then-exec git exemption ───────────────────────────────────────────


class TestWriteThenExecGitExempt:
    """Git commands referencing written files are NOT blocked."""

    def test_git_add_written_ts_file(self, tmp_project: Path) -> None:
        """Agent writes .ts file then git adds it — allowed."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        ex.execute("write_file", {
            "path": "src/data-loader.ts",
            "content": "export function loadData() { return {}; }",
        })
        result = ex.execute("run_command", {
            "command": "git add src/data-loader.ts",
        })
        assert isinstance(result, str)  # not blocked

    def test_git_commit_after_write(self, tmp_project: Path) -> None:
        """Agent writes file, git adds and commits — allowed."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        ex.execute("write_file", {
            "path": "src/app.ts",
            "content": "console.log('hello');",
        })
        result = ex.execute("run_command", {
            "command": "git add -A && git commit -m 'add app' --allow-empty",
        })
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_non_git_exec_of_written_file_still_blocked(self, tmp_project: Path) -> None:
        """Running a written .ts file via node is still blocked."""
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        ex.execute("write_file", {
            "path": "src/evil.ts",
            "content": "process.exit(1);",
        })
        with pytest.raises(ToolCallBlocked, match="Write-then-exec"):
            ex.execute("run_command", {"command": "npx tsx src/evil.ts"})


    def test_cat_pipe_head_translated(self, tmp_project: Path) -> None:
        """cat file | head -100 extracts path correctly (no pipe in path)."""
        (tmp_project / "data").mkdir(exist_ok=True)
        (tmp_project / "data" / "seed.json").write_text('{"test": true}')
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("run_command", {
            "command": "cat data/seed.json | head -100",
        })
        parsed = json.loads(result)
        assert "content" in parsed
        assert "test" in parsed["content"]

    def test_head_pipe_grep_translated(self, tmp_project: Path) -> None:
        """head -50 file | grep pattern → read_file(file)."""
        (tmp_project / "src" / "index.ts").write_text("export const x = 1;\n")
        ex = BuildAgentExecutor(tmp_project, allowed_runtimes={"node"})
        result = ex.execute("run_command", {
            "command": "head -50 src/index.ts | grep export",
        })
        parsed = json.loads(result)
        assert "content" in parsed
