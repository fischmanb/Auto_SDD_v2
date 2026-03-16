"""Prompt templates for pre-build phases 1-5.

Each phase has a system prompt (role + rules) and a user prompt
(input artifacts + task). Phase 6 (RED) is deterministic — no agent,
no prompts.
"""
from __future__ import annotations

from pathlib import Path


def _read_if_exists(path: Path) -> str:
    """Read file content or return empty string."""
    if path.exists():
        return path.read_text()
    return ""


# ── Shared rules ─────────────────────────────────────────────────────────────

SHARED_AGENT_RULES = (
    "RULES:\n"
    "- Call tools one at a time (no parallel calls)\n"
    "- Write the output file(s) specified below\n"
    "- Commit your work with git add + git commit when done\n"
    "- After committing, emit these signals on separate lines:\n"
    "    FEATURE_BUILT: <phase name>\n"
    "    SPEC_FILE: <path to the primary output file>\n"
    "    SOURCE_FILES: <comma-separated list of files created/modified>\n"
    "- Do NOT run tests\n"
    "- Do NOT modify existing files unless instructed\n"
    "- Do NOT use git push, git merge, git rebase, or git checkout\n"
)


# ── Phase 1: VISION ──────────────────────────────────────────────────────────


def vision_system_prompt(project_dir: Path) -> str:
    return (
        "You are a product analyst. Your job is to produce a structured "
        "vision document for a software project.\n\n"
        f"{SHARED_AGENT_RULES}\n"
        f"Project root: {project_dir}\n"
    )


def vision_user_prompt(project_dir: Path, user_input: str) -> str:
    return (
        "Create .specs/vision.md with these sections:\n"
        "- Overview (what the app is, one paragraph)\n"
        "- Target Users (who it's for)\n"
        "- Problem Statement (what problem it solves)\n"
        "- Key Screens / Areas (table: Screen | Purpose | Priority)\n"
        "- Tech Stack (table: Layer | Technology)\n"
        "- Design Principles (numbered list)\n"
        "- Out of Scope\n\n"
        "Create the .specs/ directory if it doesn't exist.\n\n"
        f"User input:\n{user_input}\n"
    )


# ── Phase 2: SYSTEMS DESIGN ──────────────────────────────────────────────────


def systems_design_system_prompt(project_dir: Path) -> str:
    return (
        "You are a software architect. Your job is to define consistent "
        "implementation patterns for a software project based on its vision.\n\n"
        f"{SHARED_AGENT_RULES}\n"
        f"Project root: {project_dir}\n"
    )


def systems_design_user_prompt(project_dir: Path) -> str:
    vision = _read_if_exists(project_dir / ".specs" / "vision.md")
    return (
        "Create .specs/systems-design.md with these sections:\n"
        "- Directory Structure conventions\n"
        "- Shared Module locations and contracts\n"
        "- State Management pattern\n"
        "- API / Data Access pattern\n"
        "- Error Handling pattern\n"
        "- Naming Conventions\n\n"
        "Base your decisions on the tech stack and app structure "
        "described in the vision.\n\n"
        f"Vision document:\n{vision}\n"
    )


# ── Phase 3: DESIGN SYSTEM ───────────────────────────────────────────────────


def design_system_system_prompt(project_dir: Path) -> str:
    return (
        "You are a UI/UX designer. Your job is to define a design token "
        "system (colors, spacing, typography, radii) for a software project.\n\n"
        f"{SHARED_AGENT_RULES}\n"
        f"Project root: {project_dir}\n"
    )


def design_system_user_prompt(project_dir: Path) -> str:
    vision = _read_if_exists(project_dir / ".specs" / "vision.md")
    return (
        "Create .specs/design-system/tokens.md with these token categories:\n"
        "- Personality (which visual personality and why)\n"
        "- Colors (primary, hover, light, neutrals, semantic)\n"
        "- Spacing (base unit + scale)\n"
        "- Typography (font family, sizes, weights)\n"
        "- Border Radii\n"
        "- Shadows (resting + elevated)\n\n"
        "Create the .specs/design-system/ directory if needed.\n"
        "Derive choices from the vision's target users, "
        "design principles, and app personality.\n\n"
        f"Vision document:\n{vision}\n"
    )


# ── Phase 4: ROADMAP ─────────────────────────────────────────────────────────


def roadmap_system_prompt(project_dir: Path) -> str:
    return (
        "You are a project planner. Your job is to decompose a software "
        "vision into right-sized features, identify dependencies, and "
        "produce a build-ready roadmap.\n\n"
        f"{SHARED_AGENT_RULES}\n"
        f"Project root: {project_dir}\n"
    )


def roadmap_user_prompt(project_dir: Path) -> str:
    vision = _read_if_exists(project_dir / ".specs" / "vision.md")
    return (
        "Create .specs/roadmap.md with:\n"
        "- A parseable markdown table with columns: "
        "| # | Name | Domain | Deps | Complexity | Notes | Status |\n"
        "- Features grouped into named phases\n"
        "- Complexity: S (1-3 files), M (3-7 files), L (7-15 files)\n"
        "- Status: ⬜ for all new features\n"
        "- Deps: comma-separated feature names, or - for none\n"
        "- Dependencies must reference feature names exactly\n"
        "- No circular dependencies\n\n"
        "CRITICAL: The LAST feature in the roadmap MUST be an App Shell "
        "that creates the application entry point. For Next.js 14+, this "
        "means app/layout.tsx and app/page.tsx using the App Router. For "
        "other frameworks: index.html, main.tsx, App.vue, etc. This "
        "feature MUST depend on ALL other features and wire them into a "
        "single renderable application. Without this, the project compiles "
        "but has no entry point and cannot run.\n\n"
        "Scan the codebase (read package.json, src/ structure, etc.) "
        "to detect any already-built features and mark them ✅.\n\n"
        f"Vision document:\n{vision}\n"
    )


# ── Phase 5: SPEC-FIRST ──────────────────────────────────────────────────────


def spec_first_system_prompt(project_dir: Path) -> str:
    return (
        "You are a requirements analyst. Your job is to produce a "
        "structured feature specification with YAML front matter and "
        "Gherkin scenarios (Given/When/Then).\n\n"
        f"{SHARED_AGENT_RULES}\n"
        f"Project root: {project_dir}\n"
    )


def spec_first_user_prompt(
    project_dir: Path,
    feature_name: str,
    feature_domain: str,
    feature_deps: list[str],
    feature_complexity: str,
) -> str:
    vision = _read_if_exists(project_dir / ".specs" / "vision.md")
    systems = _read_if_exists(project_dir / ".specs" / "systems-design.md")
    tokens = _read_if_exists(
        project_dir / ".specs" / "design-system" / "tokens.md",
    )

    deps_str = ", ".join(feature_deps) if feature_deps else "none"

    return (
        f"Create .specs/features/{feature_domain}/"
        f"{feature_name.lower().replace(' ', '-')}.feature.md\n\n"
        "The file MUST have:\n"
        "1. YAML front matter with keys: feature, domain, status, deps, "
        "design_refs\n"
        "2. At least one Gherkin scenario with Given/When/Then steps\n"
        "3. A User Journey section (where user comes from, where they go)\n"
        "4. Design Token References section\n\n"
        "Create parent directories as needed.\n\n"
        f"Feature: {feature_name}\n"
        f"Domain: {feature_domain}\n"
        f"Complexity: {feature_complexity}\n"
        f"Dependencies: {deps_str}\n\n"
        f"Vision:\n{vision}\n\n"
        f"Systems Design:\n{systems}\n\n"
        f"Design Tokens:\n{tokens}\n"
    )
