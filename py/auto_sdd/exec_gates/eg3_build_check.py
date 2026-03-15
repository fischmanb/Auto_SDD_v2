"""EG3: Build Check ExecGate — orchestrator-side build verification.

Runs the project's build command as a subprocess and captures pass/fail.
The agent never runs build checks — this is the orchestrator's job (P1).
Deterministic: subprocess exit code = 0 is pass, anything else is fail.

Also provides detect_build_cmd() for auto-detecting the correct build
command from project files. Detection order: most-specific framework
first (Next.js), then generic language tooling (L-00177).

AgentSpec lineage: agent_finish trigger, deterministic predicate
(exit code check), binary enforce (pass/fail).
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class BuildCheckResult:
    """Result of the EG3 build check."""

    passed: bool = False
    output: str = ""
    skipped: bool = False

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "output": self.output,
            "skipped": self.skipped,
        }


def check_build(build_cmd: str, project_dir: Path) -> BuildCheckResult:
    """Run the project build command (orchestrator-side, per P1).

    This is EG3 — deterministic build verification. The agent cannot
    run builds or report build results. The orchestrator captures the
    exit code and output directly.

    Args:
        build_cmd: Shell command to run (e.g., 'npx tsc --noEmit').
            If empty or 'skip', returns a skipped result.
        project_dir: Project root directory (cwd for the subprocess).

    Returns:
        BuildCheckResult with passed, output, and skipped fields.
    """
    if not build_cmd or build_cmd == "skip":
        logger.debug("EG3 build check skipped (no build command)")
        return BuildCheckResult(passed=True, output="(build check skipped)", skipped=True)

    try:
        result = subprocess.run(
            build_cmd, shell=True,
            capture_output=True, text=True,
            cwd=str(project_dir), timeout=120,
        )
        output = result.stdout[-2000:] + result.stderr[-2000:]
        passed = result.returncode == 0

        if passed:
            logger.info("EG3 build check passed")
        else:
            logger.warning("EG3 build check failed (exit code %d)", result.returncode)

        return BuildCheckResult(passed=passed, output=output)
    except subprocess.TimeoutExpired:
        logger.warning("EG3 build check timed out after 120s")
        return BuildCheckResult(passed=False, output="Build check timed out after 120s")
    except OSError as exc:
        logger.warning("EG3 build check error: %s", exc)
        return BuildCheckResult(passed=False, output=f"Build check failed: {exc}")


# ── Detection ────────────────────────────────────────────────────────────

_NEXTJS_CONFIGS = (
    "next.config.js",
    "next.config.mjs",
    "next.config.ts",
    "next.config.cjs",
)


def detect_build_cmd(
    project_dir: Path,
    override: str | None = None,
) -> str:
    """Auto-detect the build command for a project.

    Detection order is most-specific framework first, then generic
    language tooling. Next.js must precede tsconfig because Next.js
    projects always have tsconfig.json but ``tsc --noEmit`` misses
    server/client boundary violations that ``next build`` catches
    (L-00177).

    Args:
        project_dir: Project root directory.
        override: Explicit command from config. ``"skip"`` disables.

    Returns:
        Command string, or empty string if nothing detected.
    """
    if override is not None:
        return "" if override == "skip" else override

    # ── Framework-specific (must precede generic tsconfig) ────────
    if any((project_dir / cfg).exists() for cfg in _NEXTJS_CONFIGS):
        pkg = project_dir / "package.json"
        if pkg.exists():
            try:
                if '"build"' in pkg.read_text():
                    return "npm run build"
            except OSError:
                pass

    # ── TypeScript ────────────────────────────────────────────────
    if (project_dir / "tsconfig.build.json").exists():
        return "npx tsc --noEmit --project tsconfig.build.json"
    if (project_dir / "tsconfig.json").exists():
        return "npx tsc --noEmit"

    # ── Python ────────────────────────────────────────────────────
    if (project_dir / "pyproject.toml").exists() or (
        project_dir / "setup.py"
    ).exists():
        py_files = [
            p for p in project_dir.rglob("*.py")
            if "venv" not in p.parts and ".venv" not in p.parts
        ]
        first = str(py_files[0].relative_to(project_dir)) if py_files else "main.py"
        return f"python -m py_compile {first}"

    # ── Rust ──────────────────────────────────────────────────────
    if (project_dir / "Cargo.toml").exists():
        return "cargo check"

    # ── Go ────────────────────────────────────────────────────────
    if (project_dir / "go.mod").exists():
        return "go build ./..."

    # ── Node.js with build script (generic fallback) ─────────────
    pkg = project_dir / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            if "build" in data.get("scripts", {}):
                return "npm run build"
        except (json.JSONDecodeError, OSError):
            pass

    return ""
