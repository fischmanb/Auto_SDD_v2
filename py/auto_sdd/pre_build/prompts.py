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
    "- Do NOT read files in data/ — your inputs are the .specs/ "
    "artifacts provided in this prompt. Reading data files wastes "
    "turns and bloats context.\n"
    "- Do NOT explore the project with ls or find. Everything you "
    "need is in this prompt. Start writing immediately.\n"
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
        "- Directory Structure conventions (with tree diagram)\n"
        "- Shared Module locations and contracts (with TypeScript "
        "interface definitions where applicable)\n"
        "- State Management pattern\n"
        "- API / Data Access pattern\n"
        "- Error Handling pattern\n"
        "- Naming Conventions\n\n"
        "FORMAT RULES:\n"
        "- Use tables for conventions and rules, not prose paragraphs.\n"
        "- Code examples are encouraged but keep them to the contract "
        "signatures, not full implementations.\n"
        "- One-sentence rationale per decision, max. No essays.\n"
        "- Target 150-250 lines total.\n\n"
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


# ── Phase 3b: PERSONAS ────────────────────────────────────────────────────────


def personas_system_prompt(project_dir: Path) -> str:
    return (
        "You are a UX researcher. Your job is to define concrete user "
        "personas for a software project based on its vision and visual "
        "design tokens.\n\n"
        f"{SHARED_AGENT_RULES}\n"
        f"Project root: {project_dir}\n"
    )


def personas_user_prompt(project_dir: Path) -> str:
    vision = _read_if_exists(project_dir / ".specs" / "vision.md")
    tokens = _read_if_exists(
        project_dir / ".specs" / "design-system" / "tokens.md",
    )
    return (
        "Create .specs/personas.md with 2-3 user archetypes.\n\n"
        "These are FUNCTIONAL ARCHETYPES derived from real usage "
        "patterns for this type of application. Ground them in how "
        "actual users of this category of software work — their "
        "devices, workflows, data consumption patterns, and "
        "interaction habits.\n\n"
        "Do NOT invent fictional names, ages, backstories, or "
        "medical conditions. Do NOT fabricate specific diagnoses. "
        "If accessibility considerations are relevant to the user "
        "type, state them as general design requirements (e.g., "
        "'high contrast needed for bright-room use'), not as "
        "invented personal attributes.\n\n"
        "Each archetype MUST include these fields:\n"
        "- **Role** (e.g., 'Power analyst' or 'Executive reviewer')\n"
        "- **Goals** (what they need from the app, 2-3 bullets)\n"
        "- **Device context** (screen size range, typical environment, "
        "and how it affects what they can see)\n"
        "- **Density preference** (high/medium/low — how much data "
        "on screen at once, with one sentence on why)\n"
        "- **Critical interactions** (sort, filter, drill-down, "
        "compare, scan, etc.)\n"
        "- **Design implication** (2-3 sentences: what this archetype "
        "means for layout, spacing, typography, and hierarchy "
        "decisions. Reference specific tokens where relevant.)\n\n"
        "The design implication field is the most important. It must "
        "be specific enough that a build agent can use it to resolve "
        "a tradeoff like 'should this table use py-2 or py-3 cells?'\n\n"
        "End with a summary table: archetype | density | primary "
        "screen | key interaction | top design implication.\n\n"
        f"Vision document:\n{vision}\n\n"
        f"Design Tokens:\n{tokens}\n"
    )


# ── Phase 3c: DESIGN PATTERNS ────────────────────────────────────────────────


def design_patterns_system_prompt(project_dir: Path) -> str:
    return (
        "You are a senior UI/UX designer. Your job is to produce a "
        "structured design system document that defines layout rules, "
        "component anatomy, interaction states, spacing relationships, "
        "and responsive behavior — grounded in the project's design "
        "tokens and user personas.\n\n"
        f"{SHARED_AGENT_RULES}\n"
        f"Project root: {project_dir}\n"
    )


def design_patterns_user_prompt(project_dir: Path) -> str:
    vision = _read_if_exists(project_dir / ".specs" / "vision.md")
    tokens = _read_if_exists(
        project_dir / ".specs" / "design-system" / "tokens.md",
    )
    personas = _read_if_exists(project_dir / ".specs" / "personas.md")
    return (
        "Create .specs/design-system/patterns.md\n\n"
        "This document defines HOW tokens are applied — not what the "
        "token values are (that's in tokens.md).\n\n"
        "FORMAT RULES:\n"
        "- Use tables for token-to-usage mappings, not prose.\n"
        "- No ASCII art diagrams. A one-line description is enough.\n"
        "- No rationale paragraphs — one sentence per decision, max.\n"
        "- Include animation/transition specs that improve the feel "
        "of the UI (hover fades, focus rings, loading skeletons, "
        "state changes). Omit gratuitous animation (bouncing, "
        "parallax, decorative page transitions).\n"
        "- Target 200-300 lines total. Cut anything a build agent "
        "doesn't need to write correct CSS/Tailwind.\n\n"
        "Required sections:\n\n"
        "## Layout Grid\n"
        "Table: columns, gutters, margins, max-width, centering. "
        "One row per property.\n\n"
        "## Component Anatomy\n"
        "For each component type used in this app (card, table, chart "
        "container, nav, etc.), a table mapping: property → token → "
        "Tailwind class. Include padding, gap, border, shadow, radius.\n\n"
        "## Spacing Relationships\n"
        "Table: relationship (section-to-section, card-to-card, "
        "heading-to-content, etc.) → token → Tailwind class.\n"
        "ALL values must reference tokens from tokens.md.\n\n"
        "## Interaction States\n"
        "Table per interactive element type (button, table row, sort "
        "header): state → background → text → border → shadow.\n"
        "States: default, hover, active, focus, disabled.\n"
        "Plus global patterns for: loading (skeleton), empty, error — "
        "one table each.\n\n"
        "## Density & Space\n"
        "State the default density choice and why (reference personas). "
        "Table: compact vs standard spacing for each context. "
        "Minimum click target sizes.\n\n"
        "## Responsive Behavior\n"
        "Table: breakpoint → min-width → what changes. "
        "List what collapses, stacks, or hides.\n\n"
        "## Overflow & Clipping\n"
        "Table: context (table cell, card title, numeric value, chart "
        "axis) → truncate/wrap/scroll → implementation.\n"
        "Z-index layers: table with layer → z-index → elements.\n\n"
        f"Vision document:\n{vision}\n\n"
        f"Design Tokens:\n{tokens}\n\n"
        f"User Archetypes:\n{personas}\n"
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
    personas = _read_if_exists(project_dir / ".specs" / "personas.md")
    patterns = _read_if_exists(
        project_dir / ".specs" / "design-system" / "patterns.md",
    )

    deps_str = ", ".join(feature_deps) if feature_deps else "none"

    return (
        f"Create .specs/features/{feature_domain}/"
        f"{feature_name.lower().replace(' ', '-')}.feature.md\n\n"
        "The file MUST have:\n"
        "1. YAML front matter with keys: feature, domain, status, deps, "
        "design_refs, interaction_states\n"
        "   - interaction_states: list of UI states this feature covers "
        "(e.g., [default, loading, empty, error, hover, disabled])\n"
        "2. At least one Gherkin scenario with Given/When/Then steps\n"
        "3. A User Journey section (where user comes from, where they go)\n"
        "4. Design Token References section\n\n"
        "TOKEN ASSERTION REQUIREMENT:\n"
        "Every Gherkin scenario MUST assert specific design token values "
        "from tokens.md in its Then/And steps. Do NOT write vague "
        "assertions like 'uses the design tokens.' Instead write:\n"
        "  Then the card background MUST be `zinc-800`\n"
        "  And text uses `text-base` with color `zinc-100`\n"
        "Every UI-producing feature must have token assertions derived "
        "from tokens.md. Reference exact token names in backticks.\n\n"
        "INTERACTION STATES:\n"
        "For UI features, Gherkin scenarios must cover interaction states "
        "listed in the front matter (loading, empty, error, hover, etc.). "
        "Each state should have at least one Then/And step.\n\n"
        "LAYOUT & SPACING:\n"
        "Reference spacing tokens and layout patterns from patterns.md "
        "where applicable. Assert padding, gaps, and responsive behavior "
        "in Gherkin steps.\n\n"
        "FORMAT RULES:\n"
        "- No rationale paragraphs or prose explanations. "
        "Tables and Gherkin steps are the content.\n"
        "- User Journey: 3-5 lines max.\n"
        "- Design Token References: table format only.\n"
        "- Component mapping or data flow, if included: single table "
        "or one-line diagram each. No prose around them.\n"
        "- Include animation/transition specs that improve the feel "
        "of the UI (hover fades, focus rings, loading states). "
        "Omit gratuitous animation (bouncing, parallax, decorative "
        "page transitions).\n\n"
        "Create parent directories as needed.\n\n"
        f"Feature: {feature_name}\n"
        f"Domain: {feature_domain}\n"
        f"Complexity: {feature_complexity}\n"
        f"Dependencies: {deps_str}\n\n"
        f"Vision:\n{vision}\n\n"
        f"Systems Design:\n{systems}\n\n"
        f"Design Tokens:\n{tokens}\n\n"
        f"Design Patterns:\n{patterns}\n\n"
        f"User Personas:\n{personas}\n"
    )
